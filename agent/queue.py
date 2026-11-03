"""The queue agent: it plans a run, hands each claim to a claim agent and sums up."""

from dataclasses import dataclass
from typing import Literal

from langchain.agents import create_agent
from langchain.tools import ToolRuntime
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import tool
from pydantic import BaseModel

from agent import main
from agent.tools import reply, request

STEPS_PER_CLAIM = 20  # LangGraph steps a run allows for each claim it can take


@dataclass
class RunContext:
    """What the queue agent's tools know about the run, out of the model's hands."""

    run_id: str
    claim_llm: BaseChatModel | None


class Todo(BaseModel):
    content: str
    status: Literal["todo", "in_progress", "done", "handler"]


@tool
def list_claims() -> str:
    """List every claim in the queue, in id order, with its state."""
    return reply(request("GET", "/api/claims"))


@tool
def update_todos(todos: list[Todo], runtime: ToolRuntime[RunContext]) -> str:
    """Write the run's whole to-do list, one item for each claim you will work."""
    body = {"todos": [todo.model_dump() for todo in todos]}
    response = request("PUT", f"/api/runs/{runtime.context.run_id}/todos", body)
    return f"Saved {len(todos)} items." if response.is_success else reply(response)


@tool
def work_claim(claim_id: str, runtime: ToolRuntime[RunContext]) -> str:
    """Hand a waiting claim to a claim agent, and get back its one-line report."""
    path = f"/api/runs/{runtime.context.run_id}/claims"
    taken = request("POST", path, {"claim_id": claim_id})
    if taken.is_error:
        return reply(taken)
    line = main.work_claim(claim_id, runtime.context.claim_llm)
    print(line, flush=True)
    return line


@tool
def finish_run(summary: str, runtime: ToolRuntime[RunContext]) -> str:
    """Finish the run with a short summary for the handlers."""
    path = f"/api/runs/{runtime.context.run_id}/finish"
    response = request("POST", path, {"summary": summary})
    return "The run is finished." if response.is_success else reply(response)


QUEUE_TOOLS = [list_claims, update_todos, work_claim, finish_run]


def run_queue(
    cap: int, llm: BaseChatModel | None = None, claim_llm: BaseChatModel | None = None
) -> str:
    """Start a run of up to cap claims, let the queue agent work it, and sum it up."""
    run_id = main.call_backend("POST", "/api/runs", {"cap": cap})["run_id"]
    agent = create_agent(
        llm or main.model(),
        tools=QUEUE_TOOLS,
        system_prompt=main.call_backend("GET", "/api/instructions")["queue"],
        middleware=[main.retries()],
        context_schema=RunContext,
    )
    agent.invoke(
        {"messages": [{"role": "user", "content": f"Run {run_id}, cap {cap}"}]},
        config={"recursion_limit": STEPS_PER_CLAIM * (cap + 1)},
        context=RunContext(run_id, claim_llm),
    )
    run = main.call_backend("GET", "/api/runs/latest")
    if run["status"] != "finished":
        return f"Run {run_id} ended without finishing"
    return f"Run {run_id} finished: {run['summary']}"
