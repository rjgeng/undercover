"""The UnderCover backend."""

import json
import sqlite3
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException

from backend import db
from backend.models import (
    Claim,
    ClaimSummary,
    Customer,
    Handler,
    Policy,
    PolicyWording,
)
from backend.seed import seed

COMPANY = json.loads((db.DATA / "company.json").read_text())


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
