"""The UnderCover Agent."""

import json
import os
import uuid
from typing import Any

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.agents.middleware import ModelRetryMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import SecretStr

from agent.tools import TOOLS, request

load_dotenv(override=True)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DOCUMENTS = {"wording": "Policy wording", "manual": "Claims manual"}
DEFAULT_MODEL = "deepseek/deepseek-v4.1-flash"
MODEL_TIMEOUT = 60
RETRY_DELAY = 1.0
CLAIM_STEPS = 60  # LangGraph steps a claim agent can take, about 30 model calls
FAILED = {
    "waiting": "failed, back in the queue",
    "needs_handler": "failed twice, left for a handler",
}


def model() -> ChatOpenAI:
    """Return the model named in MODEL_NAME, or DeepSeek V4.1 Flash by default."""
    name = os.getenv("MODEL_NAME")
    return ChatOpenAI(
        model=name or DEFAULT_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
        reasoning_effort=None if name else "low",
        timeout=MODEL_TIMEOUT,
        max_retries=0,
    )


def retries() -> ModelRetryMiddleware[Any, Any]:
    """Retry a failed model call twice, with backoff, then raise its error."""
    return ModelRetryMiddleware(
        max_retries=2, initial_delay=RETRY_DELAY, on_failure="error"
    )


class BackendError(Exception):
    """The backend refused a request the agent's run depends on."""


def call_backend(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    """Call the backend and return its JSON, raising if it refuses."""
    response = request(method, path, body)
    if response.is_error:
        raise BackendError(f"{response.status_code}: {response.json()['detail']}")
    return response.json()


def read(section: dict[str, Any]) -> str:
    """Name a section the agent read, like Claims manual, section 9: Repeat claims."""
    document = DOCUMENTS[section["document"]]
    return f"{document}, section {section['number']}: {section['title']}"


def steps(message: AnyMessage) -> list[tuple[str, str]]:
    """Turn one message from the agent's run into steps for the dashboard."""
    if isinstance(message, ToolMessage):
        found = message.status == "success" and not message.text.startswith("Refused")
        if message.name == "read_section" and found:
            return [("read", read(json.loads(message.text)))]
        return [("tool_result", f"{message.name}: {message.text}")]
    found = []
    if message.text.strip():
        found.append(("message", message.text))
    if isinstance(message, AIMessage):
        for call in message.tool_calls:
            args = ", ".join(f"{k}={json.dumps(v)}" for k, v in call["args"].items())
            found.append(("tool_call", f"{call['name']}({args})"))
    return found


def run(claim_id: str, thread_id: str, llm: BaseChatModel | None = None) -> str:
    """Work one claim, recording each step with the backend, and return the reply."""
    call_backend("POST", f"/api/claims/{claim_id}/start", {"thread_id": thread_id})
    instructions = call_backend("GET", "/api/instructions")["claim"]
    agent = create_agent(
        llm or model(),
        tools=TOOLS,
        system_prompt=instructions,
        middleware=[retries()],
        checkpointer=InMemorySaver(),
    )
    states = agent.stream(
        {"messages": [{"role": "user", "content": f"Claim {claim_id}"}]},
        config={
            "configurable": {"thread_id": thread_id},
            "recursion_limit": CLAIM_STEPS,
        },
        stream_mode="values",
    )
    messages = next(states)["messages"]
    for state in states:
        for message in state["messages"][len(messages) :]:
            for kind, content in steps(message):
                call_backend(
                    "POST",
                    f"/api/claims/{claim_id}/steps",
                    {"kind": kind, "content": content},
                )
        messages = state["messages"]
    return messages[-1].text


def report(claim: dict[str, Any], error: str | None) -> str:
    """Report on a claim in one line, like CLM-1001: approve $420.00, paid."""
    decision = claim["decision"]
    if decision is None:
        state = FAILED.get(claim["status"], "not worked")
        return f"{claim['claim_id']}: {state}: {error}"
    line = f"{claim['claim_id']}: {decision['decision']} ${decision['payout']:,.2f}"
    if decision["decision"] == "approve":
        if claim["payment"]:
            line += ", paid"
        elif claim["status"] == "waiting_for_sign_off":
            line += ", waiting for sign-off"
        else:
            line += ", not paid"
    return line if error is None else f"{line}: {error}"


def work_claim(claim_id: str, llm: BaseChatModel | None = None) -> str:
    """Work one claim with a fresh claim agent, and report on it in one line."""
    error = None
    try:
        run(claim_id, str(uuid.uuid4()), llm)
    except Exception as failure:  # a claim that fails is put right, not left stuck
        error = str(failure) or type(failure).__name__
    claim = call_backend("GET", f"/api/claims/{claim_id}")
    if claim["status"] == "in_progress":
        error = error or "The agent ended without a decision"
        path = f"/api/claims/{claim_id}/failure"
        claim = call_backend("POST", path, {"reason": error})
    return report(claim, error)
