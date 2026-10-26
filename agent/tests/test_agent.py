from itertools import count
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult

from agent import main

REFUSAL = "Refused: A payout over $1,000.00 needs a handler's sign-off."
IDS = count()


class StubModel(GenericFakeChatModel):
    """A chat model that gives scripted replies in place of a real model."""

    seen: list[list[BaseMessage]] = []

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.seen.append(messages)
        return super()._generate(messages, stop, run_manager, **kwargs)


def stub(*replies: AIMessage) -> StubModel:
    return StubModel(messages=iter(replies), seen=[])


def use(name: str, text: str = "", **args: object) -> AIMessage:
    return AIMessage(
        content=text,
        tool_calls=[{"name": name, "args": args, "id": f"call-{next(IDS)}"}],
    )


def decide(claim_id: str, decision: str, payout: float, text: str = "") -> AIMessage:
    return use(
        "record_decision",
        text,
        claim_id=claim_id,
        decision=decision,
        payout=payout,
        reasons="The reasons.",
        policy_section="Section 3, Trip Delay",
    )


def reads(claim_id: str, policy_id: str, customer_id: str) -> list[AIMessage]:
    return [
        use("get_claim", claim_id=claim_id),
        use("get_policy", policy_id=policy_id),
        use("get_claim_history", customer_id=customer_id),
    ]


def steps(client, claim_id: str) -> list[dict[str, str]]:
    return client.get(f"/api/claims/{claim_id}/steps").json()


def test_run_reads_approves_and_pays(client):
    model = stub(
        *reads("CLM-1001", "POL-2001", "CUS-3001"),
        decide("CLM-1001", "approve", 420.0, "A covered delay of 19 hours."),
        use("pay_claim", claim_id="CLM-1001", amount=420.0),
        AIMessage(content="Approved and paid $420.00."),
    )
    assert main.run("CLM-1001", "thread-1", model) == "Approved and paid $420.00."
    claim = client.get("/api/claims/CLM-1001").json()
    assert claim["status"] == "decided"
    assert claim["thread_id"] == "thread-1"
    assert claim["paid_amount"] == 420.0
    recorded = steps(client, "CLM-1001")
    assert [s["title"] for s in recorded if s["kind"] == "tool"] == [
        "Read the claim",
        "Read the policy",
        "Read the claim history",
        "Record the decision",
        "Pay the claim",
    ]
    assert [s["detail"] for s in recorded if s["kind"] == "note"] == [
        "A covered delay of 19 hours.",
        "Approved and paid $420.00.",
    ]
    history = recorded[2]["detail"]
    assert "CLM-0412" in history
    assert "maya.patel@example.com" not in history


def test_run_gives_the_model_the_instructions_and_the_wording(client):
    model = stub(AIMessage(content="Nothing to do."))
    main.run("CLM-1001", "thread-1", model)
    system = model.seen[0][0].text
    assert system.startswith("# The UnderCover Agent")
    assert "# UnderCover Travel Insurance: Policy Wording" in system


def test_payment_over_the_limit_is_refused(client):
    model = stub(
        use("get_claim", claim_id="CLM-1002"),
        decide("CLM-1002", "approve", 1150.0),
        use("pay_claim", claim_id="CLM-1002", amount=1150.0),
        AIMessage(content="Approved, waiting for sign-off."),
    )
    main.run("CLM-1002", "thread-2", model)
    claim = client.get("/api/claims/CLM-1002").json()
    assert claim["status"] == "waiting_for_sign_off"
    assert claim["paid_amount"] is None
    assert steps(client, "CLM-1002")[-2]["detail"].endswith(REFUSAL)


def test_a_refused_decision_can_be_corrected(client):
    model = stub(
        decide("CLM-1001", "refer", 50.0),
        decide("CLM-1001", "refer", 0),
        AIMessage(content="Referred."),
    )
    main.run("CLM-1001", "thread-3", model)
    claim = client.get("/api/claims/CLM-1001").json()
    assert claim["status"] == "decided"
    assert claim["decision"] == "refer"
    assert steps(client, "CLM-1001")[0]["detail"].endswith(
        "Refused: A decline or a referral has a payout of $0.00"
    )


def test_a_decline_pays_nothing(client):
    model = stub(decide("CLM-1001", "decline", 0), AIMessage(content="Declined."))
    main.run("CLM-1001", "thread-4", model)
    claim = client.get("/api/claims/CLM-1001").json()
    assert claim["status"] == "decided"
    assert claim["payout"] == 0
    assert claim["paid_amount"] is None


def test_refused_reads_come_back_as_text(client):
    assert main.get_claim.invoke({"claim_id": "CLM-9999"}) == (
        "Refused: Claim CLM-9999 not found"
    )
    assert main.get_claim_history.invoke({"customer_id": "CUS-9999"}) == (
        "Refused: Customer CUS-9999 not found"
    )


def test_main_works_every_waiting_claim(client, monkeypatch, capsys):
    worked = []

    def fake_run(claim_id, thread_id):
        worked.append(claim_id)
        client.post(f"/api/claims/{claim_id}/start", json={"thread_id": thread_id})

    client.post("/api/claims/CLM-1001/start", json={"thread_id": "earlier"})
    monkeypatch.setattr(main, "run", fake_run)
    main.main([])
    assert worked == [f"CLM-{n}" for n in range(1002, 1026)]
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "CLM-1002: no decision (in progress)"
    assert len(lines) == 24


def test_main_works_named_claims(client, monkeypatch, capsys):
    def fake_run(claim_id, thread_id):
        payout = {"CLM-1001": 420.0, "CLM-1002": 1150.0}[claim_id]
        client.post(f"/api/claims/{claim_id}/start", json={"thread_id": thread_id})
        main.record_decision.invoke(
            {
                "claim_id": claim_id,
                "decision": "approve",
                "payout": payout,
                "reasons": "The reasons.",
                "policy_section": "Section 5",
            }
        )
        main.pay_claim.invoke({"claim_id": claim_id, "amount": payout})

    client.post("/api/claims/CLM-1003/start", json={"thread_id": "earlier"})
    monkeypatch.setattr(main, "run", fake_run)
    main.main(["CLM-1001", "CLM-1002", "CLM-1003", "CLM-9999"])
    assert capsys.readouterr().out.splitlines() == [
        "CLM-1001: approve $420.00 (decided, paid)",
        "CLM-1002: approve $1,150.00 (waiting for sign-off)",
        "CLM-1003: skipped, it's in progress",
        "CLM-9999: skipped, it's not in the queue",
    ]


def test_model_name(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("MODEL_NAME", raising=False)
    assert main.model().model_name == "openai/gpt-6-luna"
    monkeypatch.setenv("MODEL_NAME", "openrouter/free")
    assert main.model().model_name == "openrouter/free"
