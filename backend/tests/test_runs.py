import sqlite3
from contextlib import closing

import pytest

from backend.tests.test_workflow import decide, pay, start


def leave_waiting(database, *claim_ids):
    """Decide every claim in the queue except the ones named."""
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("UPDATE claims SET status = 'decided'")
        db.executemany(
            "UPDATE claims SET status = 'waiting' WHERE claim_id = ?",
            [(claim_id,) for claim_id in claim_ids],
        )


def start_run(client, cap):
    return client.post("/api/runs", json={"cap": cap}).json()


def take(client, run_id, claim_id):
    return client.post(f"/api/runs/{run_id}/claims", json={"claim_id": claim_id})


def fail(client, claim_id, reason="The model timed out"):
    return client.post(f"/api/claims/{claim_id}/failure", json={"reason": reason})


def finish(client, run_id, summary="Worked the queue."):
    return client.post(f"/api/runs/{run_id}/finish", json={"summary": summary})


def todos(client, run_id, items):
    return client.put(f"/api/runs/{run_id}/todos", json={"todos": items})


def test_no_run_yet(client):
    response = client.get("/api/runs/latest")
    assert response.status_code == 200
    assert response.json() is None


def test_start_run(client):
    run = start_run(client, 2)
    assert run["run_id"].startswith("RUN-")
    assert (run["cap"], run["status"], run["todos"], run["claims"]) == (
        2,
        "running",
        [],
        [],
    )
    assert run["summary"] is None
    assert run["started_at"]
    assert run["finished_at"] is None
    assert client.get("/api/runs/latest").json() == run


def test_a_run_needs_a_cap(client):
    assert client.post("/api/runs", json={"cap": 0}).status_code == 422


def test_take_claims_within_the_cap(client):
    run_id = start_run(client, 2)["run_id"]
    assert take(client, run_id, "CLM-1001").status_code == 200
    assert take(client, run_id, "CLM-1002").json()["claims"] == [
        "CLM-1001",
        "CLM-1002",
    ]
    response = take(client, run_id, "CLM-1003")
    assert response.status_code == 409
    assert response.json()["detail"] == f"Run {run_id} has taken its cap of 2 claims"


def test_a_cap_of_one_claim(client):
    run_id = start_run(client, 1)["run_id"]
    take(client, run_id, "CLM-1001")
    response = take(client, run_id, "CLM-1002")
    assert response.json()["detail"] == f"Run {run_id} has taken its cap of 1 claim"


def test_a_run_takes_its_own_claim_again(client):
    run_id = start_run(client, 1)["run_id"]
    take(client, run_id, "CLM-1001")
    start(client, "CLM-1001")
    fail(client, "CLM-1001")
    response = take(client, run_id, "CLM-1001")
    assert response.status_code == 200
    assert response.json()["claims"] == ["CLM-1001"]


def test_take_claim_refusals(client):
    run_id = start_run(client, 5)["run_id"]
    start(client, "CLM-1001")
    response = take(client, run_id, "CLM-1001")
    assert response.status_code == 409
    assert response.json()["detail"] == "Claim CLM-1001 is not waiting"
    assert take(client, run_id, "CLM-9999").status_code == 404
    assert take(client, "RUN-missing", "CLM-1002").status_code == 404


def test_take_claim_needs_a_running_run(client):
    run_id = start_run(client, 1)["run_id"]
    take(client, run_id, "CLM-1001")
    start(client, "CLM-1001")
    decide(client, "CLM-1001", "decline", 0)
    finish(client, run_id)
    response = take(client, run_id, "CLM-1002")
    assert response.status_code == 409
    assert response.json()["detail"] == f"Run {run_id} is finished"


def test_update_todos(client):
    run_id = start_run(client, 2)["run_id"]
    items = [
        {"content": "Work CLM-1002", "status": "in_progress"},
        {"content": "Work CLM-1001", "status": "todo"},
    ]
    response = todos(client, run_id, items)
    assert response.status_code == 200
    assert response.json()["todos"] == items
    assert client.get("/api/runs/latest").json()["todos"] == items


@pytest.mark.parametrize(
    "item",
    [
        {"content": "Work CLM-1001", "status": "maybe"},
        {"content": "", "status": "todo"},
    ],
)
def test_todos_must_be_valid(client, item):
    run_id = start_run(client, 2)["run_id"]
    assert todos(client, run_id, [item]).status_code == 422
    assert client.get("/api/runs/latest").json()["todos"] == []


def test_todos_need_a_running_run(client):
    assert todos(client, "RUN-missing", []).status_code == 404
    run_id = start_run(client, 1)["run_id"]
    start_run(client, 1)
    assert todos(client, run_id, []).status_code == 409


def test_a_claim_that_fails_goes_back_in_the_queue_then_to_a_handler(client):
    start(client, "CLM-1001")
    claim = fail(client, "CLM-1001").json()
    assert (claim["status"], claim["failures"]) == ("waiting", 1)
    steps = client.get("/api/claims/CLM-1001/steps").json()
    assert [(s["kind"], s["content"]) for s in steps] == [
        ("error", "The model timed out")
    ]

    start(client, "CLM-1001")
    claim = fail(client, "CLM-1001", "The backend timed out").json()
    assert (claim["status"], claim["failures"]) == ("needs_handler", 2)
    assert start(client, "CLM-1001").status_code == 409
    assert client.get("/api/claims").json()[0]["status"] == "needs_handler"


def test_fail_claim_refusals(client):
    assert fail(client, "CLM-1001").status_code == 409
    assert fail(client, "CLM-9999").status_code == 404
    start(client, "CLM-1001")
    assert fail(client, "CLM-1001", "").status_code == 422


def test_nothing_is_decided_or_paid_twice(client):
    start(client, "CLM-1001")
    decide(client, "CLM-1001", "approve", 420.0)
    assert fail(client, "CLM-1001").status_code == 409
    assert decide(client, "CLM-1001", "decline", 0).status_code == 409
    assert pay(client, "CLM-1001", 420.0).status_code == 200
    assert pay(client, "CLM-1001", 420.0).status_code == 409
    claim = client.get("/api/claims/CLM-1001").json()
    assert (claim["status"], claim["failures"]) == ("decided", 0)


def test_finish_refuses_while_its_own_claim_waits(client):
    run_id = start_run(client, 1)["run_id"]
    take(client, run_id, "CLM-1001")
    start(client, "CLM-1001")
    fail(client, "CLM-1001")
    response = finish(client, run_id)
    assert response.status_code == 409
    assert response.json()["detail"] == (
        f"Run {run_id} has missed waiting claims: CLM-1001"
    )


def test_finish_refuses_while_there_is_room_and_a_claim_waits(client, database):
    leave_waiting(database, "CLM-1001", "CLM-1002", "CLM-1003")
    run_id = start_run(client, 3)["run_id"]
    for claim_id in ("CLM-1001", "CLM-1002"):
        take(client, run_id, claim_id)
        start(client, claim_id)
        decide(client, claim_id, "decline", 0)
    response = finish(client, run_id)
    assert response.status_code == 409
    assert response.json()["detail"] == (
        f"Run {run_id} has missed waiting claims: CLM-1003"
    )


def test_finish_run(client):
    run_id = start_run(client, 1)["run_id"]
    take(client, run_id, "CLM-1001")
    start(client, "CLM-1001")
    decide(client, "CLM-1001", "approve", 420.0)
    assert finish(client, run_id, "").status_code == 422
    run = finish(client, run_id, "One claim approved.").json()
    assert (run["status"], run["summary"]) == ("finished", "One claim approved.")
    assert run["finished_at"]
    assert finish(client, run_id).status_code == 409
    assert finish(client, "RUN-missing").status_code == 404


def test_finish_with_room_left_and_nothing_waiting(client, database):
    leave_waiting(database, "CLM-1001", "CLM-1002")
    run_id = start_run(client, 3)["run_id"]
    for claim_id in ("CLM-1001", "CLM-1002"):
        take(client, run_id, claim_id)
        start(client, claim_id)
        decide(client, claim_id, "refer", 0)
    assert finish(client, run_id).json()["status"] == "finished"


def test_starting_a_run_stops_an_unfinished_one(client):
    old = start_run(client, 2)["run_id"]
    take(client, old, "CLM-1001")
    start(client, "CLM-1001")
    start(client, "CLM-1002")

    new = start_run(client, 2)["run_id"]

    assert client.get("/api/runs/latest").json()["run_id"] == new
    claim = client.get("/api/claims/CLM-1001").json()
    assert (claim["status"], claim["failures"]) == ("waiting", 1)
    steps = client.get("/api/claims/CLM-1001/steps").json()
    assert steps[-1]["kind"] == "error"
    assert steps[-1]["content"] == f"Run {old} stopped before the claim was decided"
    assert client.get("/api/claims/CLM-1002").json()["status"] == "in_progress"
    assert take(client, old, "CLM-1003").json()["detail"] == f"Run {old} is stopped"
