"""The UnderCover backend."""

import json
import sqlite3
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException

from backend import db
from backend.models import (
    Claim,
    ClaimSummary,
    Customer,
    Handler,
    NewDecision,
    NewStep,
    Payment,
    Policy,
    PolicyWording,
    SignOff,
    StartClaim,
    Step,
)
from backend.seed import seed

COMPANY = json.loads((db.DATA / "company.json").read_text())
LIMIT: float = COMPANY["payout_approval_limit"]
LABELS = {
    "waiting": "waiting",
    "in_progress": "in progress",
    "waiting_for_sign_off": "waiting for sign-off",
    "decided": "decided",
}


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Seed the database on start when its file is missing."""
    if not db.path().exists():
        seed()
    yield


app = FastAPI(title="UnderCover", lifespan=lifespan)


def connection() -> Iterator[sqlite3.Connection]:
    """Open a connection for one request, and commit if the request succeeds."""
    conn = db.connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


Conn = Annotated[sqlite3.Connection, Depends(connection)]


def found(row: sqlite3.Row | None, what: str) -> sqlite3.Row:
    """Return the row, or answer 404 when there isn't one."""
    if row is None:
        raise HTTPException(404, f"{what} not found")
    return row


def merged(row: sqlite3.Row) -> dict[str, object]:
    """Combine a claim's record from data/ with its state columns."""
    return json.loads(row["record"]) | dict(row)


def now() -> str:
    """Return the time now in UTC, to the second."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def money(amount: float) -> str:
    """Format an amount in US dollars, such as $1,250.00."""
    return f"${amount:,.2f}"


def find_claim(conn: sqlite3.Connection, claim_id: str) -> Claim:
    """Load a claim with its state."""
    row = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,))
    return Claim.model_validate(merged(found(row.fetchone(), f"Claim {claim_id}")))


@app.get("/api/health", operation_id="health")
def health() -> dict[str, str]:
    """Check that the backend is running."""
    return {"status": "ok"}


@app.get("/api/claims", operation_id="list_claims")
def list_claims(conn: Conn) -> list[ClaimSummary]:
    """List every claim in the queue with where it stands."""
    rows = conn.execute(
        "SELECT claims.*, json_extract(customers.record, '$.name') AS customer_name"
        " FROM claims JOIN customers USING (customer_id) ORDER BY claim_id"
    )
    return [ClaimSummary.model_validate(merged(row)) for row in rows]


@app.get("/api/claims/{claim_id}", operation_id="get_claim")
def get_claim(claim_id: str, conn: Conn) -> Claim:
    """Get a claim in full, with its decision, sign-off and payment."""
    return find_claim(conn, claim_id)


@app.get("/api/policies/{policy_id}", operation_id="get_policy")
def get_policy(policy_id: str, conn: Conn) -> Policy:
    """Get a policy: its plan, add-ons, trip and travelers."""
    row = conn.execute("SELECT record FROM policies WHERE policy_id = ?", (policy_id,))
    return Policy.model_validate_json(found(row.fetchone(), f"Policy {policy_id}")[0])


@app.get("/api/customers/{customer_id}", operation_id="get_customer")
def get_customer(customer_id: str, conn: Conn) -> Customer:
    """Get a customer, with their earlier claims."""
    row = conn.execute(
        "SELECT record FROM customers WHERE customer_id = ?", (customer_id,)
    )
    return Customer.model_validate_json(
        found(row.fetchone(), f"Customer {customer_id}")[0]
    )


@app.get("/api/handlers", operation_id="list_handlers")
def list_handlers(conn: Conn) -> list[Handler]:
    """List the claims handlers."""
    rows = conn.execute("SELECT record FROM handlers ORDER BY handler_id")
    return [Handler.model_validate_json(row[0]) for row in rows]


@app.get("/api/policy-wording", operation_id="get_policy_wording")
def get_policy_wording() -> PolicyWording:
    """Get the policy wording that decisions follow."""
    return PolicyWording(
        version=COMPANY["policy_wording_version"],
        text=(db.DATA / "policy_wording.md").read_text(),
    )


@app.post("/api/claims/{claim_id}/start", operation_id="start_claim")
def start_claim(claim_id: str, body: StartClaim, conn: Conn) -> Claim:
    """Start work on a waiting claim, on the agent's thread."""
    claim = find_claim(conn, claim_id)
    if claim.status != "waiting":
        raise HTTPException(
            409, f"Claim {claim_id} is {LABELS[claim.status]}, so it can't be started"
        )
    conn.execute(
        "UPDATE claims SET status = 'in_progress', thread_id = ? WHERE claim_id = ?",
        (body.thread_id, claim_id),
    )
    return find_claim(conn, claim_id)


@app.post("/api/claims/{claim_id}/steps", operation_id="add_step")
def add_step(claim_id: str, body: NewStep, conn: Conn) -> Step:
    """Record a step the agent took on a claim."""
    find_claim(conn, claim_id)
    row = conn.execute(
        "INSERT INTO steps (claim_id, kind, title, detail, created_at)"
        " VALUES (?, ?, ?, ?, ?) RETURNING *",
        (claim_id, body.kind, body.title, body.detail, now()),
    ).fetchone()
    return Step.model_validate(dict(row))


@app.get("/api/claims/{claim_id}/steps", operation_id="list_steps")
def list_steps(claim_id: str, conn: Conn) -> list[Step]:
    """List the agent's steps on a claim, oldest first."""
    find_claim(conn, claim_id)
    rows = conn.execute(
        "SELECT * FROM steps WHERE claim_id = ? ORDER BY step_id", (claim_id,)
    )
    return [Step.model_validate(dict(row)) for row in rows]


@app.post("/api/claims/{claim_id}/decision", operation_id="record_decision")
def record_decision(claim_id: str, body: NewDecision, conn: Conn) -> Claim:
    """Record the decision on a claim in progress, which is final."""
    claim = find_claim(conn, claim_id)
    if claim.status != "in_progress":
        raise HTTPException(
            409,
            f"Claim {claim_id} is {LABELS[claim.status]}, so it can't take a decision",
        )
    if body.decision != "approve" and body.payout:
        raise HTTPException(422, "A decline or a referral has a payout of $0.00")
    held = body.decision == "approve" and body.payout > LIMIT
    conn.execute(
        "UPDATE claims SET status = ?, decision = ?, payout = ?, reasons = ?,"
        " policy_section = ?, decided_at = ? WHERE claim_id = ?",
        (
            "waiting_for_sign_off" if held else "decided",
            body.decision,
            body.payout,
            body.reasons,
            body.policy_section,
            now(),
            claim_id,
        ),
    )
    return find_claim(conn, claim_id)


@app.post("/api/claims/{claim_id}/payment", operation_id="pay_claim")
def pay_claim(claim_id: str, body: Payment, conn: Conn) -> Claim:
    """Pay an approved claim its payout, once signed off if over the limit."""
    claim = find_claim(conn, claim_id)
    if claim.decision != "approve" or claim.payout is None:
        raise HTTPException(409, f"Claim {claim_id} has no approval to pay")
    if claim.payout > LIMIT and claim.signed_off_by is None:
        raise HTTPException(
            403, f"A payout over {money(LIMIT)} needs a handler's sign-off."
        )
    if claim.paid_amount is not None:
        raise HTTPException(409, f"Claim {claim_id} is already paid")
    if body.amount != claim.payout:
        raise HTTPException(
            409, f"The amount must be the approved payout of {money(claim.payout)}"
        )
    conn.execute(
        "UPDATE claims SET paid_amount = ?, paid_at = ? WHERE claim_id = ?",
        (body.amount, now(), claim_id),
    )
    return find_claim(conn, claim_id)


@app.post("/api/claims/{claim_id}/sign-off", operation_id="sign_off_claim")
def sign_off_claim(claim_id: str, body: SignOff, conn: Conn) -> Claim:
    """Sign off an approval over the limit as a handler, which pays it."""
    claim = find_claim(conn, claim_id)
    row = conn.execute(
        "SELECT record FROM handlers WHERE handler_id = ?", (body.handler_id,)
    )
    handler = Handler.model_validate_json(
        found(row.fetchone(), f"Handler {body.handler_id}")[0]
    )
    if claim.status != "waiting_for_sign_off":
        raise HTTPException(
            409, f"Claim {claim_id} is {LABELS[claim.status]}, not waiting for sign-off"
        )
    if not handler.can_approve_over_limit:
        raise HTTPException(
            403, f"{handler.name} can't sign off payouts over {money(LIMIT)}"
        )
    signed_at = now()
    conn.execute(
        "UPDATE claims SET status = 'decided', signed_off_by = ?, signed_off_at = ?,"
        " paid_amount = payout, paid_at = ? WHERE claim_id = ?",
        (handler.handler_id, signed_at, signed_at, claim_id),
    )
    return find_claim(conn, claim_id)
