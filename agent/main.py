"""The UnderCover Agent."""

import json
import os
from typing import Any, Literal
from uuid import uuid4

import httpx
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, ToolCall, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

load_dotenv(override=True)

BACKEND_URL = "http://localhost:8000"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openai/gpt-6-luna"
TITLES = {
    "get_claim": "Read the claim",
    "get_policy": "Read the policy",
    "get_claim_history": "Read the claim history",
    "record_decision": "Record the decision",
    "pay_claim": "Pay the claim",
}
LABELS = {
    "waiting": "waiting",
    "in_progress": "in progress",
    "waiting_for_sign_off": "waiting for sign-off",
    "decided": "decided",
}


def backend() -> httpx.Client:
    """Return a client for the UnderCover backend."""
    return httpx.Client(base_url=BACKEND_URL, timeout=10)


def send(method: str, path: str, body: dict[str, Any] | None = None) -> httpx.Response:
    """Send one request to the backend."""
    with backend() as client:
        return client.request(method, path, json=body)


def fetch(path: str) -> Any:
    """Get a record from the backend."""
    return send("GET", path).raise_for_status().json()


def call(method: str, path: str, body: dict[str, Any] | None = None) -> str:
    """Call the backend for a tool, giving a refusal back as text, not an error."""
    response = send(method, path, body)
    if response.is_client_error:
        return f"Refused: {response.json()['detail']}"
    return response.raise_for_status().text


@tool
def get_claim(claim_id: str) -> str:
    """Read a claim: the customer's story, the items claimed and the documents."""
    return call("GET", f"/api/claims/{claim_id}")


@tool
def get_policy(policy_id: str) -> str:
    """Read a policy: its plan, add-ons, purchase date, trip and travelers."""
    return call("GET", f"/api/policies/{policy_id}")


@tool
def get_claim_history(customer_id: str) -> str:
    """Read the customer's earlier claims."""
    reply = call("GET", f"/api/customers/{customer_id}")
    if reply.startswith("Refused"):
        return reply
    return json.dumps(json.loads(reply)["previous_claims"])


@tool
def record_decision(
    claim_id: str,
    decision: Literal["approve", "decline", "refer"],
    payout: float,
    reasons: str,
    policy_section: str,
) -> str:
    """Record the final decision on a claim, with its payout, reasons and section."""
    return call(
        "POST",
        f"/api/claims/{claim_id}/decision",
        {
            "decision": decision,
            "payout": payout,
            "reasons": reasons,
            "policy_section": policy_section,
        },
    )


@tool
def pay_claim(claim_id: str, amount: float) -> str:
    """Pay an approved claim its payout."""
    return call("POST", f"/api/claims/{claim_id}/payment", {"amount": amount})


TOOLS = [get_claim, get_policy, get_claim_history, record_decision, pay_claim]


def model() -> ChatOpenAI:
    """Return the model named in MODEL_NAME, or GPT-6 Luna by default."""
    name = os.getenv("MODEL_NAME")
    return ChatOpenAI(
        model=name or DEFAULT_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
        reasoning_effort=None if name else "low",
    )


def record(claim_id: str, message: AnyMessage, calls: dict[str, ToolCall]) -> None:
    """Record a tool's result, or the model's text, as a step on the claim."""
    if isinstance(message, ToolMessage):
        used = calls[message.tool_call_id]
        step = {
            "kind": "tool",
            "title": TITLES.get(used["name"], used["name"]),
            "detail": f"{json.dumps(used['args'])}\n\n{message.text}",
        }
    elif message.text:
        step = {"kind": "note", "title": "Note", "detail": message.text}
    else:
        return
    send("POST", f"/api/claims/{claim_id}/steps", step).raise_for_status()


def run(claim_id: str, thread_id: str, llm: BaseChatModel | None = None) -> str:
    """Work one claim and return the agent's final reply."""
    start = send("POST", f"/api/claims/{claim_id}/start", {"thread_id": thread_id})
    start.raise_for_status()
    instructions = fetch("/api/instructions")["text"]
    wording = fetch("/api/policy-wording")["text"]
    agent = create_agent(
        llm or model(), tools=TOOLS, system_prompt=f"{instructions}\n\n{wording}"
    )
    calls: dict[str, ToolCall] = {}
    reply = ""
    for update in agent.stream(
        {"messages": [{"role": "user", "content": f"Please decide claim {claim_id}."}]},
        config={"configurable": {"thread_id": thread_id}},
        stream_mode="updates",
    ):
        for node in update.values():
            for message in node["messages"]:
                if isinstance(message, AIMessage):
                    calls |= {str(used["id"]): used for used in message.tool_calls}
                    reply = message.text or reply
                record(claim_id, message, calls)
    return reply


def outcome(claim_id: str) -> str:
    """Say in one line how a claim ended up."""
    claim = fetch(f"/api/claims/{claim_id}")
    status = LABELS[claim["status"]]
    if claim["decision"] is None:
        return f"{claim_id}: no decision ({status})"
    paid = ", paid" if claim["paid_amount"] is not None else ""
    return f"{claim_id}: {claim['decision']} ${claim['payout']:,.2f} ({status}{paid})"


def main(claim_ids: list[str]) -> None:
    """Work the named claims, or every waiting claim in the queue."""
    statuses = {claim["claim_id"]: claim["status"] for claim in fetch("/api/claims")}
    waiting = [claim_id for claim_id, s in statuses.items() if s == "waiting"]
    for claim_id in claim_ids or waiting:
        if claim_id not in waiting:
            where = LABELS.get(statuses.get(claim_id, ""), "not in the queue")
            print(f"{claim_id}: skipped, it's {where}")
            continue
        run(claim_id, f"{claim_id}-{uuid4().hex[:8]}")
        print(outcome(claim_id))
