import httpx
import pytest
from langchain_core.messages import AIMessage

from agent import main, tools
from agent.tests.test_agent import call, script, stub
from agent.tools import backend as real_backend

TIMEOUT = TimeoutError("The model timed out")


def claim_of(client, claim_id):
    return client.get(f"/api/claims/{claim_id}").json()


def kinds(client, claim_id):
    return [step["kind"] for step in client.get(f"/api/claims/{claim_id}/steps").json()]


def test_a_paid_approval(client):
    pay = call("pay_claim", claim_id="CLM-1001", amount=420.0)
    model = script("CLM-1001", "POL-2001", "CUS-3001", "approve", 420.0, pay)
    assert main.work_claim("CLM-1001", model) == "CLM-1001: approve $420.00, paid"


def test_an_approval_waiting_for_sign_off(client):
    model = script("CLM-1002", "POL-2002", "CUS-3002", "approve", 1350.0)
    assert main.work_claim("CLM-1002", model) == (
        "CLM-1002: approve $1,350.00, waiting for sign-off"
    )


def test_a_referral(client):
    model = script("CLM-1003", "POL-2003", "CUS-3003", "refer", 0)
    assert main.work_claim("CLM-1003", model) == "CLM-1003: refer $0.00"


def test_a_claim_that_fails_goes_back_in_the_queue_then_to_a_handler(client):
    line = main.work_claim("CLM-1001", stub(TIMEOUT, TIMEOUT, TIMEOUT))
    assert line == "CLM-1001: failed, back in the queue: The model timed out"
    claim = claim_of(client, "CLM-1001")
    assert (claim["status"], claim["failures"]) == ("waiting", 1)
    assert kinds(client, "CLM-1001") == ["error"]

    line = main.work_claim("CLM-1001", stub(TIMEOUT, TIMEOUT, TIMEOUT))
    assert line == ("CLM-1001: failed twice, left for a handler: The model timed out")
    claim = claim_of(client, "CLM-1001")
    assert (claim["status"], claim["failures"]) == ("needs_handler", 2)


def test_an_agent_that_ends_without_a_decision_has_failed(client):
    model = stub(call("get_claim", claim_id="CLM-1001"), AIMessage("It's covered."))
    assert main.work_claim("CLM-1001", model) == (
        "CLM-1001: failed, back in the queue: The agent ended without a decision"
    )
    assert kinds(client, "CLM-1001") == ["tool_call", "tool_result", "message", "error"]


def test_blank_messages_are_not_recorded(client):
    model = script("CLM-1003", "POL-2003", "CUS-3003", "refer", 0)
    first = call("get_claim", text="\n\n", claim_id="CLM-1003")
    model.messages = iter([first, *list(model.messages)[1:]])
    main.work_claim("CLM-1003", model)
    steps = client.get("/api/claims/CLM-1003/steps").json()
    assert all(step["content"].strip() for step in steps)
    assert kinds(client, "CLM-1003")[0] == "tool_call"


def test_a_model_that_fails_once_is_tried_again(client):
    model = script("CLM-1003", "POL-2003", "CUS-3003", "decline", 0)
    model.messages = iter([TIMEOUT, *model.messages])
    assert main.work_claim("CLM-1003", model) == "CLM-1003: decline $0.00"
    assert claim_of(client, "CLM-1003")["failures"] == 0


def test_a_tool_that_fails_fails_the_claim(client, monkeypatch):
    def unreachable(response):
        raise httpx.ConnectError("The backend is unreachable")

    monkeypatch.setattr(tools, "reply", unreachable)
    model = stub(call("get_claim", claim_id="CLM-1001"))
    assert main.work_claim("CLM-1001", model) == (
        "CLM-1001: failed, back in the queue: The backend is unreachable"
    )
    assert claim_of(client, "CLM-1001")["status"] == "waiting"


def test_a_failure_after_the_decision_keeps_the_decision(client):
    model = script("CLM-1001", "POL-2001", "CUS-3001", "approve", 420.0)
    model.messages = iter([*list(model.messages)[:-1], TIMEOUT, TIMEOUT, TIMEOUT])
    assert main.work_claim("CLM-1001", model) == (
        "CLM-1001: approve $420.00, not paid: The model timed out"
    )
    claim = claim_of(client, "CLM-1001")
    assert (claim["status"], claim["failures"], claim["payment"]) == (
        "decided",
        0,
        None,
    )


def test_a_claim_that_isnt_waiting_is_not_worked(client):
    main.work_claim("CLM-1003", script("CLM-1003", "POL-2003", "CUS-3003", "refer", 0))
    assert main.work_claim("CLM-1003", stub()) == (
        "CLM-1003: refer $0.00: 409: Claim CLM-1003 is not waiting"
    )
    assert claim_of(client, "CLM-1003")["failures"] == 0


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        (None, "http://127.0.0.1:8000"),
        ("http://127.0.0.1:8001", "http://127.0.0.1:8001"),
    ],
)
def test_the_backend_address(monkeypatch, address, expected):
    if address is None:
        monkeypatch.delenv("UNDERCOVER_API", raising=False)
    else:
        monkeypatch.setenv("UNDERCOVER_API", address)
    with real_backend() as client:
        assert str(client.base_url) == expected
