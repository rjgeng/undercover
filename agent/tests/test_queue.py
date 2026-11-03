import sqlite3
from contextlib import closing

import pytest
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool

from agent import __main__ as cli
from agent.queue import QUEUE_TOOLS, run_queue
from agent.tests.test_agent import call, stub

TIMEOUT = TimeoutError("The model timed out")


def leave_waiting(database, *claim_ids):
    """Decide every claim in the queue except the ones named."""
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("UPDATE claims SET status = 'decided'")
        db.executemany(
            "UPDATE claims SET status = 'waiting' WHERE claim_id = ?",
            [(claim_id,) for claim_id in claim_ids],
        )


@pytest.fixture
def three_waiting(database):
    leave_waiting(database, "CLM-1001", "CLM-1002", "CLM-1003")


def decide(claim_id, decision, payout, *extra):
    """A claim agent's script for deciding one claim."""
    return [
        call("get_claim", claim_id=claim_id),
        call(
            "record_decision",
            claim_id=claim_id,
            decision=decision,
            payout=payout,
            section="Wording section 3, Trip Delay",
            reason="Covered.",
        ),
        *extra,
        AIMessage("Done."),
    ]


def todos(*items):
    """A to-do list from (claim id, status) pairs."""
    return [
        {"content": f"Work {claim_id}", "status": status} for claim_id, status in items
    ]


def run(client):
    return client.get("/api/runs/latest").json()


def claim(client, claim_id):
    return client.get(f"/api/claims/{claim_id}").json()


def refusal(detail):
    """The reply a tool gives when the backend refuses with a 409."""
    return f'Refused with status 409: {{"detail":"{detail}"}}'


def tool_replies(model):
    """Every tool reply the queue agent was given, in order."""
    last = model.prompts[-1]
    return [message.text for message in last if isinstance(message, ToolMessage)]


def test_the_queue_agents_tools():
    names = [t.name for t in QUEUE_TOOLS]
    assert names == ["list_claims", "update_todos", "work_claim", "finish_run"]
    inputs = {
        t.name: set(convert_to_openai_tool(t)["function"]["parameters"]["properties"])
        for t in QUEUE_TOOLS
    }
    assert inputs == {
        "list_claims": set(),
        "update_todos": {"todos"},
        "work_claim": {"claim_id"},
        "finish_run": {"summary"},
    }


def test_a_whole_run(client, capsys, three_waiting):
    queue = stub(
        call("list_claims"),
        call(
            "update_todos",
            todos=todos(
                ("CLM-1001", "todo"), ("CLM-1002", "todo"), ("CLM-1003", "todo")
            ),
        ),
        call("work_claim", claim_id="CLM-1001"),
        call("work_claim", claim_id="CLM-1002"),
        call("work_claim", claim_id="CLM-1003"),
        call(
            "update_todos",
            todos=todos(
                ("CLM-1001", "done"), ("CLM-1002", "handler"), ("CLM-1003", "handler")
            ),
        ),
        call("finish_run", summary="One paid, one held for sign-off, one referred."),
        AIMessage("Finished."),
    )
    claims = stub(
        *decide(
            "CLM-1001",
            "approve",
            420.0,
            call("pay_claim", claim_id="CLM-1001", amount=420.0),
        ),
        *decide("CLM-1002", "approve", 1350.0),
        *decide("CLM-1003", "refer", 0),
    )
    summary = run_queue(3, queue, claims)

    finished = run(client)
    held = "One paid, one held for sign-off, one referred."
    assert summary == f"Run {finished['run_id']} finished: {held}"
    assert finished["status"] == "finished"
    assert finished["claims"] == ["CLM-1001", "CLM-1002", "CLM-1003"]
    assert finished["todos"] == todos(
        ("CLM-1001", "done"), ("CLM-1002", "handler"), ("CLM-1003", "handler")
    )
    assert capsys.readouterr().out.splitlines() == [
        "CLM-1001: approve $420.00, paid",
        "CLM-1002: approve $1,350.00, waiting for sign-off",
        "CLM-1003: refer $0.00",
    ]
    assert tool_replies(queue)[1:] == [
        "Saved 3 items.",
        "CLM-1001: approve $420.00, paid",
        "CLM-1002: approve $1,350.00, waiting for sign-off",
        "CLM-1003: refer $0.00",
        "Saved 3 items.",
        "The run is finished.",
    ]


def test_the_queue_agent_gets_its_instructions(client, three_waiting):
    queue = stub(AIMessage("Nothing to do."))
    run_queue(3, queue, stub())
    system = queue.prompts[0][0]
    assert isinstance(system, SystemMessage)
    assert system.content == client.get("/api/instructions").json()["queue"]
    assert queue.prompts[0][1].text == f"Run {run(client)['run_id']}, cap 3"


def test_a_run_that_doesnt_finish_says_so(client, three_waiting):
    assert run_queue(3, stub(AIMessage("I stopped early.")), stub()) == (
        f"Run {run(client)['run_id']} ended without finishing"
    )


def test_the_cap(client, database):
    leave_waiting(database, "CLM-1001", "CLM-1002", "CLM-1003", "CLM-1004", "CLM-1005")
    queue = stub(
        call("work_claim", claim_id="CLM-1001"),
        call("work_claim", claim_id="CLM-1002"),
        call("work_claim", claim_id="CLM-1003"),
        call("finish_run", summary="Two claims declined."),
        AIMessage("Finished."),
    )
    claims = stub(*decide("CLM-1001", "decline", 0), *decide("CLM-1002", "decline", 0))
    run_queue(2, queue, claims)

    run_id = run(client)["run_id"]
    assert tool_replies(queue)[2] == refusal(
        f"Run {run_id} has taken its cap of 2 claims"
    )
    assert run(client)["status"] == "finished"
    for claim_id in ("CLM-1003", "CLM-1004", "CLM-1005"):
        assert claim(client, claim_id)["status"] == "waiting"


def test_a_failed_claim_doesnt_stop_the_run_and_is_tried_again(client, database):
    leave_waiting(database, "CLM-1001", "CLM-1002")
    queue = stub(
        call("work_claim", claim_id="CLM-1001"),
        call("work_claim", claim_id="CLM-1002"),
        call("work_claim", claim_id="CLM-1001"),
        call("finish_run", summary="Two claims declined, one after a retry."),
        AIMessage("Finished."),
    )
    claims = stub(
        TIMEOUT,
        TIMEOUT,
        TIMEOUT,
        *decide("CLM-1002", "decline", 0),
        *decide("CLM-1001", "decline", 0),
    )
    run_queue(2, queue, claims)

    assert tool_replies(queue)[:3] == [
        "CLM-1001: failed, back in the queue: The model timed out",
        "CLM-1002: decline $0.00",
        "CLM-1001: decline $0.00",
    ]
    first = claim(client, "CLM-1001")
    assert (first["status"], first["failures"]) == ("decided", 1)
    assert run(client)["status"] == "finished"


def test_a_claim_that_fails_twice_is_left_for_a_handler(client, database):
    leave_waiting(database, "CLM-1001")
    queue = stub(
        call("work_claim", claim_id="CLM-1001"),
        call("work_claim", claim_id="CLM-1001"),
        call("update_todos", todos=todos(("CLM-1001", "handler"))),
        call("finish_run", summary="CLM-1001 failed twice and needs a handler."),
        AIMessage("Finished."),
    )
    run_queue(1, queue, stub(*[TIMEOUT] * 6))

    assert tool_replies(queue)[1] == (
        "CLM-1001: failed twice, left for a handler: The model timed out"
    )
    assert claim(client, "CLM-1001")["status"] == "needs_handler"
    finished = run(client)
    assert (finished["status"], finished["todos"]) == (
        "finished",
        todos(("CLM-1001", "handler")),
    )


def test_the_check_for_missed_claims(client, database):
    leave_waiting(database, "CLM-1001", "CLM-1002")
    queue = stub(
        call("work_claim", claim_id="CLM-1001"),
        call("finish_run", summary="Too soon."),
        call("work_claim", claim_id="CLM-1002"),
        call("finish_run", summary="Both claims declined."),
        AIMessage("Finished."),
    )
    claims = stub(*decide("CLM-1001", "decline", 0), *decide("CLM-1002", "decline", 0))
    run_queue(2, queue, claims)

    run_id = run(client)["run_id"]
    missed = f"Run {run_id} has missed waiting claims: CLM-1002"
    assert tool_replies(queue)[1] == refusal(missed)
    finished = run(client)
    assert (finished["status"], finished["summary"]) == (
        "finished",
        "Both claims declined.",
    )


@pytest.mark.parametrize(("args", "cap"), [(["--cap", "5"], 5), ([], 3)])
def test_command_line_runs(monkeypatch, capsys, three_waiting, args, cap):
    caps = []
    monkeypatch.setattr(
        cli, "run_queue", lambda cap: caps.append(cap) or "Run finished."
    )
    cli.main(args)
    assert caps == [cap]
    assert capsys.readouterr().out == "Run finished.\n"


def test_command_line_with_nothing_waiting(monkeypatch, capsys, database):
    leave_waiting(database)
    monkeypatch.setattr(cli, "run_queue", lambda cap: pytest.fail("no run expected"))
    cli.main([])
    assert capsys.readouterr().out == "No claims are waiting.\n"


def test_a_run_cant_finish_with_an_item_still_open(client, database):
    leave_waiting(database, "CLM-1001")
    queue = stub(
        call("update_todos", todos=todos(("CLM-1001", "in_progress"))),
        call("work_claim", claim_id="CLM-1001"),
        call("finish_run", summary="Too soon."),
        call("update_todos", todos=todos(("CLM-1001", "done"))),
        call("finish_run", summary="One claim declined."),
        AIMessage("Finished."),
    )
    run_queue(1, queue, stub(*decide("CLM-1001", "decline", 0)))

    run_id = run(client)["run_id"]
    still_open = f"Run {run_id} has to-do items still open: Work CLM-1001"
    assert tool_replies(queue)[2] == refusal(still_open)
    finished = run(client)
    assert (finished["status"], finished["todos"]) == (
        "finished",
        todos(("CLM-1001", "done")),
    )
