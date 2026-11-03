import threading
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from backend.main import app

CLAIMS = [f"CLM-10{number:02d}" for number in range(1, 9)]


def at_once(send, items):
    """Send one request per item, all released at the same moment."""
    barrier = threading.Barrier(len(items))

    def go(item):
        barrier.wait()
        return send(TestClient(app), item).status_code

    with ThreadPoolExecutor(len(items)) as pool:
        return sorted(pool.map(go, items))


def test_the_cap_holds_when_claims_are_taken_at_once(client):
    for _ in range(5):
        run_id = client.post("/api/runs", json={"cap": 1}).json()["run_id"]
        path = f"/api/runs/{run_id}/claims"
        codes = at_once(
            lambda c, claim_id, path=path: c.post(path, json={"claim_id": claim_id}),
            CLAIMS,
        )
        assert codes == [200] + [409] * 7
        assert len(client.get("/api/runs/latest").json()["claims"]) == 1


def test_a_claim_is_started_once_when_started_at_once(client):
    codes = at_once(
        lambda c, thread_id: c.post(
            "/api/claims/CLM-1001/start", json={"thread_id": thread_id}
        ),
        [f"thread-{number}" for number in range(8)],
    )
    assert codes == [200] + [409] * 7
