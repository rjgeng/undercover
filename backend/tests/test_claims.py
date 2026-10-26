import json
import sqlite3

import pytest

from backend import db, main
from backend.models import NewDecision, Payment, SignOff, StartClaim

REFUSAL = "A payout over $1,000.00 needs a handler's sign-off."


def start(client, claim_id):
    return client.post(f"/api/claims/{claim_id}/start", json={"thread_id": "t-1"})


def decide(client, claim_id, decision, payout):
    return client.post(
        f"/api/claims/{claim_id}/decision",
        json={
            "decision": decision,
            "payout": payout,
            "reasons": "The reasons.",
            "policy_section": "Section 3, Trip Delay",
        },
    )


def pay(client, claim_id, amount):
    return client.post(f"/api/claims/{claim_id}/payment", json={"amount": amount})


def sign_off(client, claim_id, handler_id):
    return client.post(
        f"/api/claims/{claim_id}/sign-off", json={"handler_id": handler_id}
    )


def approved(client, claim_id, payout):
    start(client, claim_id)
    return decide(client, claim_id, "approve", payout).json()


def test_start_claim(client):
    claim = start(client, "CLM-1001").json()
    assert claim["status"] == "in_progress"
    assert claim["thread_id"] == "t-1"


def test_start_refuses_a_claim_that_isnt_waiting(client):
    start(client, "CLM-1001")
    response = start(client, "CLM-1001")
    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Claim CLM-1001 is in progress, so it can't be started"
    )


def test_start_a_missing_claim(client):
    assert start(client, "CLM-9999").status_code == 404


@pytest.mark.parametrize("decision", ["decline", "refer"])
def test_decline_and_refer_are_decided(client, decision):
    start(client, "CLM-1001")
    claim = decide(client, "CLM-1001", decision, 0).json()
    assert claim["status"] == "decided"
    assert claim["decision"] == decision
    assert claim["payout"] == 0
    assert claim["reasons"] == "The reasons."
    assert claim["policy_section"] == "Section 3, Trip Delay"
    assert claim["decided_at"]


def test_approval_up_to_the_limit_is_decided_then_paid(client):
    assert approved(client, "CLM-1001", 420.0)["status"] == "decided"
    claim = pay(client, "CLM-1001", 420.0).json()
    assert claim["paid_amount"] == 420.0
    assert claim["paid_at"]


def test_approval_over_the_limit_waits_and_cant_be_paid(client):
    assert approved(client, "CLM-1002", 1150.0)["status"] == "waiting_for_sign_off"
    for amount in [1150.0, 1000.0]:
        response = pay(client, "CLM-1002", amount)
        assert response.status_code == 403
        assert response.json()["detail"] == REFUSAL
    assert client.get("/api/claims/CLM-1002").json()["paid_amount"] is None


def test_sign_off_decides_and_pays(client):
    approved(client, "CLM-1002", 1150.0)
    claim = sign_off(client, "CLM-1002", "HND-01").json()
    assert claim["status"] == "decided"
    assert claim["signed_off_by"] == "HND-01"
    assert claim["signed_off_at"]
    assert claim["paid_amount"] == 1150.0
    assert pay(client, "CLM-1002", 1150.0).status_code == 409


def test_exactly_the_limit_needs_no_sign_off(client):
    assert approved(client, "CLM-1001", 1000.00)["status"] == "decided"
    assert pay(client, "CLM-1001", 1000.00).status_code == 200
    assert approved(client, "CLM-1002", 1000.01)["status"] == "waiting_for_sign_off"


def test_amounts_are_rounded_to_cents(client):
    assert approved(client, "CLM-1001", 420.004)["payout"] == 420.0
    assert pay(client, "CLM-1001", 419.996).json()["paid_amount"] == 420.0


def test_decision_refusals(client):
    assert decide(client, "CLM-1001", "approve", 420.0).status_code == 409
    start(client, "CLM-1001")
    assert decide(client, "CLM-1001", "approve", -50.0).status_code == 422
    decide(client, "CLM-1001", "decline", 0)
    response = decide(client, "CLM-1001", "approve", 420.0)
    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Claim CLM-1001 is decided, so it can't take a decision"
    )


@pytest.mark.parametrize("decision", ["decline", "refer"])
def test_decline_and_refer_have_no_payout(client, decision):
    start(client, "CLM-1001")
    response = decide(client, "CLM-1001", decision, 50.0)
    assert response.status_code == 422
    assert response.json()["detail"] == "A decline or a referral has a payout of $0.00"


def test_an_approval_has_a_payout(client):
    start(client, "CLM-1001")
    response = decide(client, "CLM-1001", "approve", 0)
    assert response.status_code == 422
    assert response.json()["detail"] == "An approval has a payout above $0.00"
    assert client.get("/api/claims/CLM-1001").json()["status"] == "in_progress"


def test_the_queue_shows_decisions(client):
    approved(client, "CLM-1001", 420.0)
    claim = client.get("/api/claims").json()[0]
    assert (claim["status"], claim["decision"], claim["payout"]) == (
        "decided",
        "approve",
        420.0,
    )


@pytest.mark.parametrize("field", ["reasons", "policy_section"])
@pytest.mark.parametrize("text", ["", "   "])
def test_a_decision_needs_reasons_and_a_section(client, field, text):
    start(client, "CLM-1001")
    body = {
        "decision": "approve",
        "payout": 420.0,
        "reasons": "The reasons.",
        "policy_section": "Section 3",
    }
    response = client.post("/api/claims/CLM-1001/decision", json=body | {field: text})
    assert response.status_code == 422
    assert client.get("/api/claims/CLM-1001").json()["status"] == "in_progress"


def test_a_start_needs_a_thread_id(client):
    response = client.post("/api/claims/CLM-1001/start", json={"thread_id": ""})
    assert response.status_code == 422


def step(client, claim_id, title="Read the claim", detail="{}"):
    return client.post(
        f"/api/claims/{claim_id}/steps",
        json={"kind": "tool", "title": title, "detail": detail},
    )


def test_steps_need_a_started_claim_and_text(client):
    response = step(client, "CLM-1001")
    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Claim CLM-1001 is waiting, so it can't take a step"
    )
    start(client, "CLM-1001")
    assert step(client, "CLM-1001", title="").status_code == 422
    assert step(client, "CLM-1001", detail=" ").status_code == 422
    decide(client, "CLM-1001", "decline", 0)
    assert step(client, "CLM-1001").status_code == 200


def test_payment_refusals(client):
    start(client, "CLM-1001")
    assert pay(client, "CLM-1001", 420.0).json()["detail"] == (
        "Claim CLM-1001 has no approval to pay"
    )
    decide(client, "CLM-1001", "approve", 420.0)
    response = pay(client, "CLM-1001", 400.0)
    assert response.status_code == 409
    assert response.json()["detail"] == (
        "The amount must be the approved payout of $420.00"
    )
    pay(client, "CLM-1001", 420.0)
    response = pay(client, "CLM-1001", 420.0)
    assert response.status_code == 409
    assert response.json()["detail"] == "Claim CLM-1001 is already paid"


def test_declined_claim_cant_be_paid(client):
    start(client, "CLM-1001")
    decide(client, "CLM-1001", "decline", 0)
    assert pay(client, "CLM-1001", 0).status_code == 409


def test_sign_off_refusals(client):
    approved(client, "CLM-1001", 420.0)
    response = sign_off(client, "CLM-1001", "HND-01")
    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Claim CLM-1001 is decided, not waiting for sign-off"
    )
    approved(client, "CLM-1002", 1150.0)
    response = sign_off(client, "CLM-1002", "HND-99")
    assert response.status_code == 404
    assert response.json()["detail"] == "Handler HND-99 not found"


def test_sign_off_needs_a_handler_who_can_approve_over_the_limit(client):
    trainee = {
        "handler_id": "HND-09",
        "name": "Sam Trainee",
        "role": "Trainee",
        "email": "sam.trainee@undercover.example",
        "can_approve_over_limit": False,
    }
    with sqlite3.connect(db.path()) as conn:
        conn.execute(
            "INSERT INTO handlers VALUES (?, ?)", ("HND-09", json.dumps(trainee))
        )
    approved(client, "CLM-1002", 1150.0)
    response = sign_off(client, "CLM-1002", "HND-09")
    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Sam Trainee can't sign off payouts over $1,000.00"
    )
    assert client.get("/api/claims/CLM-1002").json()["status"] == (
        "waiting_for_sign_off"
    )


def test_steps_come_back_in_order(client):
    start(client, "CLM-1001")
    for title in ["Read the claim", "Read the policy"]:
        response = client.post(
            "/api/claims/CLM-1001/steps",
            json={"kind": "tool", "title": title, "detail": "{}"},
        )
        assert response.json()["title"] == title
    steps = client.get("/api/claims/CLM-1001/steps").json()
    assert [s["title"] for s in steps] == ["Read the claim", "Read the policy"]
    assert steps[0]["step_id"] < steps[1]["step_id"]
    assert client.get("/api/claims/CLM-9999/steps").status_code == 404


DECISION = NewDecision(
    decision="approve", payout=420.0, reasons="The reasons.", policy_section="3"
)
WRITES = {
    "start_claim": lambda conn: main.start_claim(
        "CLM-1001", StartClaim(thread_id="t-2"), conn
    ),
    "record_decision": lambda conn: main.record_decision("CLM-1002", DECISION, conn),
    "pay_claim": lambda conn: main.pay_claim("CLM-1001", Payment(amount=1.0), conn),
    "sign_off_claim": lambda conn: main.sign_off_claim(
        "CLM-1001", SignOff(handler_id="HND-01"), conn
    ),
}


@pytest.mark.parametrize("write", WRITES.values(), ids=WRITES.keys())
def test_writes_take_the_lock_before_they_check(client, write):
    start(client, "CLM-1001")
    other = db.connect()
    other.execute("BEGIN IMMEDIATE")
    conn = db.connect()
    conn.execute("PRAGMA busy_timeout = 0")
    try:
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            write(conn)
    finally:
        other.rollback()
        other.close()
        conn.close()
