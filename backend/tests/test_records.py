import sqlite3

from fastapi.testclient import TestClient

from backend import db
from backend.main import app
from backend.seed import seed


def test_seed_reports_what_it_loaded(client):
    assert seed() == "Seeded 25 claims, 50 policies, 49 customers and 3 handlers."


def test_list_claims(client):
    claims = client.get("/api/claims").json()
    assert [c["claim_id"] for c in claims] == [f"CLM-{n}" for n in range(1001, 1026)]
    assert {c["status"] for c in claims} == {"waiting"}
    assert claims[0]["customer_name"] == "Maya Patel"
    assert claims[0]["decision"] is None


def test_get_claim(client):
    claim = client.get("/api/claims/CLM-1001").json()
    assert len(claim["items"]) == 3
    assert len(claim["documents"]) == 4
    assert claim["amount_claimed"] == 420.0
    assert claim["customer_id"] == "CUS-3001"
    assert claim["status"] == "waiting"
    assert claim["decision"] is None


def test_every_record_reads(client):
    for summary in client.get("/api/claims").json():
        claim = client.get(f"/api/claims/{summary['claim_id']}").json()
        assert client.get(f"/api/policies/{claim['policy_id']}").status_code == 200
        assert client.get(f"/api/customers/{claim['customer_id']}").status_code == 200


def test_missing_records(client):
    for path, detail in [
        ("/api/claims/CLM-9999", "Claim CLM-9999 not found"),
        ("/api/policies/POL-9999", "Policy POL-9999 not found"),
        ("/api/customers/CUS-9999", "Customer CUS-9999 not found"),
    ]:
        response = client.get(path)
        assert response.status_code == 404
        assert response.json() == {"detail": detail}


def test_get_policy(client):
    policy = client.get("/api/policies/POL-2001").json()
    assert policy["plan"] == "premium"
    assert policy["trip"]["destination"] == "Rome, Italy"


def test_get_customer(client):
    customer = client.get("/api/customers/CUS-3001").json()
    assert customer["name"] == "Maya Patel"
    assert [c["claim_id"] for c in customer["previous_claims"]] == ["CLM-0412"]


def test_list_handlers(client):
    handlers = client.get("/api/handlers").json()
    assert [h["name"] for h in handlers] == [
        "Dana Whitfield",
        "Marcus Oyelaran",
        "Priya Raman",
    ]


def test_policy_wording(client):
    wording = client.get("/api/policy-wording").json()
    assert wording["version"] == "2026.1"
    assert wording["text"].startswith("# UnderCover Travel Insurance: Policy Wording")


def test_instructions(client):
    text = client.get("/api/instructions").json()["text"]
    assert text.startswith("# The UnderCover Agent")
    assert "manual" not in text


def test_reseed_resets_the_queue_in_place(client):
    with sqlite3.connect(db.path()) as conn:
        conn.execute("UPDATE claims SET status = 'decided'")
    seed()
    assert {c["status"] for c in client.get("/api/claims").json()} == {"waiting"}


def test_backend_seeds_a_missing_database(tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERCOVER_DB", str(tmp_path / "new.db"))
    with TestClient(app) as client:
        assert len(client.get("/api/claims").json()) == 25
