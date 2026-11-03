"""The UnderCover backend."""

import json
import sqlite3
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request

from backend.database import connect, database_path, seed
from backend.documents import NAMES, contents, given, split
from backend.models import (
    Claim,
    ClaimSummary,
    Decision,
    DecisionRequest,
    FailureRequest,
    FinishRequest,
    Handler,
    Instructions,
    Payment,
    PaymentRequest,
    Policy,
    PreviousClaim,
    Run,
    RunRequest,
    Section,
    SignOffRequest,
    StartRequest,
    Step,
    StepRequest,
    TakeRequest,
    TodosRequest,
)

INSTRUCTIONS = Path(__file__).parent / "instructions"
ATTEMPTS = 2  # a claim that fails this many times is left for a handler


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Seed the database on startup if it doesn't exist yet."""
    if not database_path().exists():
        seed(database_path())
    yield


app = FastAPI(title="UnderCover", lifespan=lifespan)


def database(request: Request) -> Iterator[sqlite3.Connection]:
    """Open the database for one request and commit if the request succeeds."""
    with closing(connect()) as connection, connection:
        if request.method != "GET":
            # Take the write lock first, so two requests can't both pass a check,
            # such as a run's cap, before either has written.
            connection.execute("BEGIN IMMEDIATE")
        yield connection


Database = Annotated[sqlite3.Connection, Depends(database)]


def now() -> str:
    """Return the current time in UTC, to the second."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def dollars(amount: float) -> str:
    """Format an amount like $1,250.00."""
    return f"${amount:,.2f}"


def approval_limit(db: sqlite3.Connection) -> float:
    """Return the largest payout that can be paid without a handler's sign-off."""
    return db.execute("SELECT payout_approval_limit FROM settings").fetchone()[0]


def documents(db: sqlite3.Connection) -> dict[str, str]:
    """Return the policy wording and the claims manual."""
    row = db.execute("SELECT policy_wording, claims_manual FROM settings").fetchone()
    return {"wording": row["policy_wording"], "manual": row["claims_manual"]}


def find_claim(db: sqlite3.Connection, claim_id: str) -> sqlite3.Row:
    """Return one claim's row, or raise a 404."""
    row = db.execute(
        "SELECT * FROM claim_view WHERE claim_id = ?", (claim_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"Claim {claim_id} not found")
    return row


def to_summary(row: sqlite3.Row) -> ClaimSummary:
    """Build a claim's line in the queue from its row."""
    return ClaimSummary(
        **json.loads(row["record"])
        | {
            "status": row["status"],
            "customer_name": row["customer_name"],
            "decision": row["decision"],
            "payout": row["payout"],
        }
    )


def to_claim(row: sqlite3.Row) -> Claim:
    """Build a claim in full, with its decision and payment, from its row."""
    decision = None
    if row["decision"] is not None:
        decision = Decision(**{field: row[field] for field in Decision.model_fields})
    payment = None
    if row["paid_at"] is not None:
        payment = Payment(**{field: row[field] for field in Payment.model_fields})
    return Claim(
        **json.loads(row["record"])
        | {
            "status": row["status"],
            "customer_name": row["customer_name"],
            "thread_id": row["thread_id"],
            "failures": row["failures"],
            "decision": decision,
            "payment": payment,
        }
    )


def pay(
    db: sqlite3.Connection, claim_id: str, amount: float, signed_off_by: str | None
) -> Payment:
    """Record a payment on a claim."""
    payment = Payment(amount=amount, paid_at=now(), signed_off_by=signed_off_by)
    db.execute(
        "INSERT INTO payments VALUES (?, ?, ?, ?)",
        (claim_id, payment.amount, payment.paid_at, payment.signed_off_by),
    )
    return payment


def record_failure(db: sqlite3.Connection, claim_id: str, reason: str) -> None:
    """Put a claim in progress back in the queue, or leave it for a handler."""
    claim = find_claim(db, claim_id)
    failures = claim["failures"] + 1
    db.execute(
        "INSERT INTO steps (claim_id, thread_id, kind, content, created_at)"
        " VALUES (?, ?, 'error', ?, ?)",
        (claim_id, claim["thread_id"], reason, now()),
    )
    db.execute(
        "UPDATE claims SET status = ?, failures = ? WHERE claim_id = ?",
        ("needs_handler" if failures >= ATTEMPTS else "waiting", failures, claim_id),
    )


def find_run(db: sqlite3.Connection, run_id: str) -> sqlite3.Row:
    """Return one run's row, or raise a 404."""
    row = db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"Run {run_id} not found")
    return row


def running_run(db: sqlite3.Connection, run_id: str) -> sqlite3.Row:
    """Return a run that is still running, or raise a 409."""
    run = find_run(db, run_id)
    if run["status"] != "running":
        raise HTTPException(409, f"Run {run_id} is {run['status']}")
    return run


def run_claims(db: sqlite3.Connection, run_id: str) -> list[str]:
    """Return the claims a run has taken, in the order it took them."""
    rows = db.execute(
        "SELECT claim_id FROM run_claims WHERE run_id = ? ORDER BY rowid", (run_id,)
    ).fetchall()
    return [row["claim_id"] for row in rows]


def to_run(db: sqlite3.Connection, row: sqlite3.Row) -> Run:
    """Build a run, with its to-do list and its claims, from its row."""
    return Run(
        **dict(row)
        | {
            "todos": json.loads(row["todos"]),
            "claims": run_claims(db, row["run_id"]),
        }
    )


def missed_claims(db: sqlite3.Connection, run: sqlite3.Row) -> list[str]:
    """Return the waiting claims a run owes: its own, and any while it has room."""
    claims = run_claims(db, run["run_id"])
    rows = db.execute(
        "SELECT claim_id FROM claims WHERE status = 'waiting' ORDER BY claim_id"
    ).fetchall()
    waiting = [row["claim_id"] for row in rows]
    if len(claims) < run["cap"]:
        return waiting
    return [claim_id for claim_id in waiting if claim_id in claims]


def stop_unfinished_runs(db: sqlite3.Connection) -> None:
    """Stop any run left running, putting its claims in progress back in the queue."""
    for run in db.execute("SELECT run_id FROM runs WHERE status = 'running'"):
        rows = db.execute(
            "SELECT claim_id FROM run_claims JOIN claims USING (claim_id)"
            " WHERE run_id = ? AND status = 'in_progress'",
            (run["run_id"],),
        ).fetchall()
        for row in rows:
            reason = f"Run {run['run_id']} stopped before the claim was decided"
            record_failure(db, row["claim_id"], reason)
        db.execute(
            "UPDATE runs SET status = 'stopped', finished_at = ? WHERE run_id = ?",
            (now(), run["run_id"]),
        )


@app.get("/api/health", operation_id="health")
def health() -> dict[str, str]:
    """Check that the backend is running."""
    return {"status": "ok"}


@app.get("/api/claims", operation_id="list_claims")
def list_claims(db: Database) -> list[ClaimSummary]:
    """List every claim in the queue, in id order."""
    rows = db.execute("SELECT * FROM claim_view ORDER BY claim_id").fetchall()
    return [to_summary(row) for row in rows]


@app.get("/api/claims/{claim_id}", operation_id="get_claim")
def get_claim(claim_id: str, db: Database) -> Claim:
    """Get one claim in full: the story, the items claimed and the documents."""
    return to_claim(find_claim(db, claim_id))


@app.get("/api/policies/{policy_id}", operation_id="get_policy")
def get_policy(policy_id: str, db: Database) -> Policy:
    """Get a policy: the plan, add-ons, purchase date, trip and travelers."""
    row = db.execute(
        "SELECT record FROM policies WHERE policy_id = ?", (policy_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"Policy {policy_id} not found")
    return Policy(**json.loads(row["record"]))


@app.get("/api/customers/{customer_id}/claims", operation_id="get_claim_history")
def get_claim_history(customer_id: str, db: Database) -> list[PreviousClaim]:
    """Get a customer's earlier claims, with the outcome and the amount paid."""
    row = db.execute(
        "SELECT record FROM customers WHERE customer_id = ?", (customer_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"Customer {customer_id} not found")
    return [
        PreviousClaim(**claim) for claim in json.loads(row["record"])["previous_claims"]
    ]


@app.get("/api/instructions", operation_id="get_instructions")
def get_instructions(db: Database) -> Instructions:
    """Get the agent's instructions for running the queue and for working a claim."""
    texts = documents(db)
    claim = (INSTRUCTIONS / "claim.md").read_text(encoding="utf-8").strip()
    return Instructions(
        queue=(INSTRUCTIONS / "queue.md").read_text(encoding="utf-8"),
        claim="\n\n".join(
            [
                claim,
                *(given(name, text) for name, text in texts.items()),
                *(contents(name, text) for name, text in texts.items()),
            ]
        ),
    )


@app.get("/api/documents/{document}/sections/{number}", operation_id="read_section")
def read_section(document: str, number: int, db: Database) -> Section:
    """Read one section of the policy wording or the claims manual."""
    texts = documents(db)
    if document not in texts:
        raise HTTPException(404, f"Document {document} not found")
    for section in split(document, texts[document]):
        if section.number == number:
            return section
    raise HTTPException(404, f"Section {number} of the {NAMES[document]} not found")


@app.get("/api/handlers", operation_id="list_handlers")
def list_handlers(db: Database) -> list[Handler]:
    """List the claims handlers."""
    rows = db.execute("SELECT * FROM handlers ORDER BY handler_id").fetchall()
    return [Handler(**dict(row)) for row in rows]


@app.post("/api/claims/{claim_id}/start", operation_id="start_claim")
def start_claim(claim_id: str, request: StartRequest, db: Database) -> Claim:
    """Start work on a waiting claim, which moves it to in progress."""
    if find_claim(db, claim_id)["status"] != "waiting":
        raise HTTPException(409, f"Claim {claim_id} is not waiting")
    db.execute(
        "UPDATE claims SET status = 'in_progress', thread_id = ? WHERE claim_id = ?",
        (request.thread_id, claim_id),
    )
    return to_claim(find_claim(db, claim_id))


@app.post("/api/claims/{claim_id}/steps", operation_id="record_step")
def record_step(claim_id: str, request: StepRequest, db: Database) -> Step:
    """Record one step of the agent's work on a claim."""
    thread_id = find_claim(db, claim_id)["thread_id"]
    if thread_id is None:
        raise HTTPException(409, f"Claim {claim_id} has not been started")
    row = db.execute(
        "INSERT INTO steps (claim_id, thread_id, kind, content, created_at)"
        " VALUES (?, ?, ?, ?, ?) RETURNING *",
        (claim_id, thread_id, request.kind, request.content, now()),
    ).fetchone()
    return Step(**dict(row))


@app.get("/api/claims/{claim_id}/steps", operation_id="list_steps")
def list_steps(claim_id: str, db: Database) -> list[Step]:
    """List the steps of the agent's work on a claim, in order."""
    find_claim(db, claim_id)
    rows = db.execute(
        "SELECT * FROM steps WHERE claim_id = ? ORDER BY step_id", (claim_id,)
    ).fetchall()
    return [Step(**dict(row)) for row in rows]


@app.post("/api/claims/{claim_id}/decision", operation_id="record_decision")
def record_decision(claim_id: str, request: DecisionRequest, db: Database) -> Claim:
    """Record the decision on a claim; an approval over the limit waits for sign-off."""
    if find_claim(db, claim_id)["status"] != "in_progress":
        raise HTTPException(409, f"Claim {claim_id} is not in progress")
    payout = round(request.payout, 2)
    held = request.decision == "approve" and payout > approval_limit(db)
    db.execute(
        "INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?)",
        (claim_id, request.decision, payout, request.section, request.reason, now()),
    )
    db.execute(
        "UPDATE claims SET status = ? WHERE claim_id = ?",
        ("waiting_for_sign_off" if held else "decided", claim_id),
    )
    return to_claim(find_claim(db, claim_id))


@app.post("/api/claims/{claim_id}/payment", operation_id="pay_claim")
def pay_claim(claim_id: str, request: PaymentRequest, db: Database) -> Payment:
    """Pay an approved claim its payout, unless it needs a handler's sign-off."""
    claim = find_claim(db, claim_id)
    if claim["decision"] != "approve":
        raise HTTPException(409, f"Claim {claim_id} has not been approved")
    if claim["paid_at"] is not None:
        raise HTTPException(409, f"Claim {claim_id} has already been paid")
    if claim["status"] == "waiting_for_sign_off":
        raise HTTPException(
            403,
            f"A payout over {dollars(approval_limit(db))} needs a handler's sign-off",
        )
    if round(request.amount, 2) != claim["payout"]:
        raise HTTPException(
            422, f"The amount must be the approved payout of {dollars(claim['payout'])}"
        )
    return pay(db, claim_id, claim["payout"], None)


@app.post("/api/claims/{claim_id}/sign-off", operation_id="sign_off_claim")
def sign_off_claim(claim_id: str, request: SignOffRequest, db: Database) -> Claim:
    """Sign off a held payout as a handler, which pays it and decides the claim."""
    claim = find_claim(db, claim_id)
    if claim["status"] != "waiting_for_sign_off":
        raise HTTPException(409, f"Claim {claim_id} is not waiting for sign-off")
    row = db.execute(
        "SELECT * FROM handlers WHERE handler_id = ?", (request.handler_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"Handler {request.handler_id} not found")
    handler = Handler(**dict(row))
    if not handler.can_approve_over_limit:
        raise HTTPException(
            403,
            f"{handler.name} can't sign off payouts over {dollars(approval_limit(db))}",
        )
    pay(db, claim_id, claim["payout"], handler.name)
    db.execute("UPDATE claims SET status = 'decided' WHERE claim_id = ?", (claim_id,))
    return to_claim(find_claim(db, claim_id))


@app.post("/api/claims/{claim_id}/failure", operation_id="fail_claim")
def fail_claim(claim_id: str, request: FailureRequest, db: Database) -> Claim:
    """Record a failed attempt: back in the queue, or to a handler the second time."""
    if find_claim(db, claim_id)["status"] != "in_progress":
        raise HTTPException(409, f"Claim {claim_id} is not in progress")
    record_failure(db, claim_id, request.reason)
    return to_claim(find_claim(db, claim_id))


@app.post("/api/runs", operation_id="start_run")
def start_run(request: RunRequest, db: Database) -> Run:
    """Start a run of the agent, stopping any run left unfinished."""
    stop_unfinished_runs(db)
    run_id = f"RUN-{uuid.uuid4().hex[:8]}"
    db.execute(
        "INSERT INTO runs VALUES (?, ?, 'running', '[]', NULL, ?, NULL)",
        (run_id, request.cap, now()),
    )
    return to_run(db, find_run(db, run_id))


@app.get("/api/runs/latest", operation_id="get_latest_run")
def get_latest_run(db: Database) -> Run | None:
    """Get the latest run with its to-do list, or null before the first run."""
    row = db.execute("SELECT * FROM runs ORDER BY rowid DESC LIMIT 1").fetchone()
    return None if row is None else to_run(db, row)


@app.post("/api/runs/{run_id}/claims", operation_id="take_claim")
def take_claim(run_id: str, request: TakeRequest, db: Database) -> Run:
    """Take a waiting claim into a run, within the run's cap."""
    run = running_run(db, run_id)
    claim_id = request.claim_id
    if find_claim(db, claim_id)["status"] != "waiting":
        raise HTTPException(409, f"Claim {claim_id} is not waiting")
    claims = run_claims(db, run_id)
    if claim_id not in claims and len(claims) >= run["cap"]:
        noun = "claim" if run["cap"] == 1 else "claims"
        raise HTTPException(
            409, f"Run {run_id} has taken its cap of {run['cap']} {noun}"
        )
    db.execute("INSERT OR IGNORE INTO run_claims VALUES (?, ?)", (run_id, claim_id))
    return to_run(db, run)


@app.put("/api/runs/{run_id}/todos", operation_id="update_todos")
def update_todos(run_id: str, request: TodosRequest, db: Database) -> Run:
    """Replace a run's to-do list."""
    running_run(db, run_id)
    todos = json.dumps([todo.model_dump() for todo in request.todos])
    db.execute("UPDATE runs SET todos = ? WHERE run_id = ?", (todos, run_id))
    return to_run(db, find_run(db, run_id))


@app.post("/api/runs/{run_id}/finish", operation_id="finish_run")
def finish_run(run_id: str, request: FinishRequest, db: Database) -> Run:
    """Finish a run with a summary, once nothing is missed and every item is closed."""
    run = running_run(db, run_id)
    missed = missed_claims(db, run)
    if missed:
        raise HTTPException(
            409, f"Run {run_id} has missed waiting claims: {', '.join(missed)}"
        )
    still_open = [
        todo["content"]
        for todo in json.loads(run["todos"])
        if todo["status"] in ("todo", "in_progress")
    ]
    if still_open:
        raise HTTPException(
            409, f"Run {run_id} has to-do items still open: {'; '.join(still_open)}"
        )
    db.execute(
        "UPDATE runs SET status = 'finished', summary = ?, finished_at = ?"
        " WHERE run_id = ?",
        (request.summary, now(), run_id),
    )
    return to_run(db, find_run(db, run_id))
