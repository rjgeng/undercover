"""Rebuild the database from data/: uv run -m backend.seed"""

import json

from backend.db import connect, load

SCHEMA = """
DROP TABLE IF EXISTS steps;
DROP TABLE IF EXISTS claims;
DROP TABLE IF EXISTS policies;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS handlers;

CREATE TABLE handlers (handler_id TEXT PRIMARY KEY, record TEXT NOT NULL);
CREATE TABLE customers (customer_id TEXT PRIMARY KEY, record TEXT NOT NULL);
CREATE TABLE policies (policy_id TEXT PRIMARY KEY, record TEXT NOT NULL);
CREATE TABLE claims (
    claim_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers,
    record TEXT NOT NULL,
    status TEXT NOT NULL,
    thread_id TEXT,
    decision TEXT,
    payout REAL,
    reasons TEXT,
    policy_section TEXT,
    decided_at TEXT,
    signed_off_by TEXT REFERENCES handlers,
    signed_off_at TEXT,
    paid_amount REAL,
    paid_at TEXT
);
CREATE TABLE steps (
    step_id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id TEXT NOT NULL REFERENCES claims,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    detail TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def seed() -> str:
    """Drop and recreate the tables from data/ in one transaction."""
    handlers = load("handlers.json")
    customers = load("customers.json")
    policies = load("policies.json")
    claims = load("claims.json")
    conn = connect()
    try:
        conn.executescript("BEGIN;" + SCHEMA)
        conn.executemany(
            "INSERT INTO handlers VALUES (?, ?)",
            [(h["handler_id"], json.dumps(h)) for h in handlers],
        )
        conn.executemany(
            "INSERT INTO customers VALUES (?, ?)",
            [(c["customer_id"], json.dumps(c)) for c in customers],
        )
        conn.executemany(
            "INSERT INTO policies VALUES (?, ?)",
            [(p["policy_id"], json.dumps(p)) for p in policies],
        )
        conn.executemany(
            "INSERT INTO claims (claim_id, customer_id, record, status)"
            " VALUES (?, ?, ?, 'waiting')",
            [(c["claim_id"], c["customer_id"], json.dumps(c)) for c in claims],
        )
        conn.commit()
    finally:
        conn.close()
    return (
        f"Seeded {len(claims)} claims, {len(policies)} policies,"
        f" {len(customers)} customers and {len(handlers)} handlers."
    )


if __name__ == "__main__":
    print(seed())
