# Plan: the harness

This plan builds the harness in `HARNESS.md` on top of the pilot (`PLAN.md`, `STATUS.md`), in six phases. Each phase leaves `npm run check` green and is committed before the next one starts.

When it's done, one command starts a run of the UnderCover Agent. A queue agent plans the run as a to-do list, which the dashboard shows as it changes, and hands each claim to a fresh claim agent. The claim agent looks up the sections of the policy wording and the claims manual it needs, and the claim page shows what it read. A claim that fails goes back in the queue and is tried again, and a second failure leaves it for a handler. The backend makes sure a run keeps to its cap, misses no waiting claim, and never decides or pays a claim twice. The default model is DeepSeek V4.1 Flash.

## Design

### Two agents, built with LangChain

| | The queue agent | The claim agent |
| --- | --- | --- |
| Does | Plans the run, keeps the to-do list, hands out claims, checks for missed claims and writes the summary | Works one claim from a clean start |
| Tools | `list_claims`, `update_todos`, `work_claim`, `finish_run` | `get_claim`, `get_policy`, `get_claim_history`, `read_section`, `record_decision`, `pay_claim` |
| Instructions | `backend/instructions/queue.md` | `backend/instructions/claim.md`, followed by the contents of the wording and the manual |
| History it keeps | One line per claim, from `work_claim` | Its own claim only |

- Both are `create_agent` agents on the same model. No other agent framework: `deepagents` stays in the labs.
- The subagent is a tool. `work_claim` creates a new claim agent for each claim, so every claim starts from an empty history and the queue agent's history grows by one line per claim. It's the one tool not named after a backend operation, because it hands the claim to the claim agent.
- `work_claim` is the one place a claim's failure is caught. It takes the claim into the run, starts it, runs the claim agent, and records each step on the claim as the pilot does. If anything raises, or the agent ends without a decision, it records the failure with `fail_claim`. Either way it returns one line, such as `CLM-1001: approve $420.00, paid` or `CLM-1004: failed, back in the queue: the model timed out`.
- The queue agent's tools get the run id from LangChain's runtime context (`context_schema` and `ToolRuntime`), not as a tool argument, so the model can't act on another run.
- Retries happen in one place. Model calls time out after 60 seconds. `ModelRetryMiddleware` retries a failed model call twice with backoff, then raises. The OpenAI client's own retries are turned off, so a call isn't retried at two levels. A tool call that fails, such as the backend timing out, fails the claim, and the claim is tried again later in the run.
- The to-do list is our own `update_todos` tool, not LangChain's `TodoListMiddleware`. The list has to be stored in the backend so the dashboard can show it, and it needs a fourth state, left for a handler. The idea is the same: the agent writes the whole list each time it changes.

### Claim states

A new state, `needs_handler`, shown as "Needs a handler", holds a claim that failed twice before it was decided. Claims gain a count of `failures`.

| From | To | When |
| --- | --- | --- |
| `waiting` | `in_progress` | `start_claim` |
| `in_progress` | `decided` or `waiting_for_sign_off` | `record_decision`, as in the pilot |
| `in_progress` | `waiting` | `fail_claim`, the first failure |
| `in_progress` | `needs_handler` | `fail_claim`, the second failure |

Only a claim in progress can fail, so a decided claim never goes back in the queue and is never decided twice.

### Runs

- A run has an id like `RUN-1a2b3c4d`, a cap, a state (`running`, `finished` or `stopped`), a to-do list, the claims it has taken, a summary, and its start and finish times. Tables: `runs` and `run_claims`.
- The cap is the most claims a run can take. Trying one of its own claims again doesn't use another place.
- A run owes its own claims that are back in waiting, and, while it has taken fewer claims than its cap, any other waiting claim. `finish_run` refuses while a run owes anything. That's the check for missed claims, enforced in the backend. The queue agent's instructions also tell it to check before it finishes.
- `finish_run` also refuses while an item on the to-do list is still To do or In progress, so the list the handlers see is ticked off to the end. This rule was added in phase 6, after the first live run finished with its last item still In progress.
- One run at a time. `start_run` stops any run still `running`, such as one whose process was stopped, and records a failure on each of its claims that are still in progress, which puts them back in the queue. A claim worked on its own with `uv run -m agent CLM-1001` belongs to no run, and this leaves it alone.
- A to-do item has `content` and a `status`: `todo`, `in_progress`, `done` or `handler`, shown as To do, In progress, Done and Left for a handler. The agent marks a claim Done when it decides it, and Left for a handler when the claim is referred, held for sign-off or failed twice.

### API

New and changed operations. Each has an `operation_id`, a one-line docstring and no optional inputs.

| Operation | Route | What it does |
| --- | --- | --- |
| `start_run` | `POST /api/runs` | Body `{cap}`, 1 or more. Stops any unfinished run, as above, and starts a new one |
| `get_latest_run` | `GET /api/runs/latest` | The latest run with its to-do list, claims and summary, or null before the first run |
| `take_claim` | `POST /api/runs/{run_id}/claims` | Body `{claim_id}`. Takes a waiting claim into the run, within its cap |
| `update_todos` | `PUT /api/runs/{run_id}/todos` | Body `{todos}`. Replaces the run's to-do list |
| `finish_run` | `POST /api/runs/{run_id}/finish` | Body `{summary}`. Finishes the run, unless it has missed a waiting claim within its cap |
| `fail_claim` | `POST /api/claims/{claim_id}/failure` | Body `{reason}`. Records a failed attempt: back to waiting the first time, needs a handler the second |
| `read_section` | `GET /api/documents/{document}/sections/{number}` | `document` is `wording` or `manual`. One section in full: its number, title and text |
| `get_instructions` | `GET /api/instructions` | Changed: `{queue, claim}`, where `claim` ends with the contents of the wording and the manual |

Rules the backend enforces:

- `take_claim` needs a running run (409), a known claim (404) that is waiting (409), and a run under its cap unless the claim is already one of its own (409, "Run RUN-1a2b3c4d has taken its cap of 5 claims").
- `update_todos` needs a running run (409). Each item needs content, and a status that is one of the four (422).
- `finish_run` needs a running run (409) and a summary (422). While the run owes claims, it returns 409 naming them, such as "Run RUN-1a2b3c4d has missed waiting claims: CLM-1004, CLM-1005", and while a to-do item is still open it returns 409 naming the item.
- `fail_claim` needs a claim in progress (409) and a reason (422). It also records the reason on the claim as a step of kind `error`.
- `read_section` returns 404 for an unknown document or section number.
- `get_claim` adds `failures`. Steps gain two kinds: `read`, a section the agent read, and `error`, a failure.
- Everything in the pilot stands. A decision needs a claim in progress, a claim is paid once, and a payout over $1,000 waits for sign-off.

### Documents by section

- Seeding also reads `claims_manual.md` and stores it beside the wording. It still never reads `data/evals/`.
- The backend splits each document at its `## N.` headings. A section is its heading and the text up to the next heading.
- The claim agent's instructions end with the contents of both documents: each section's number and title, and the names of the notes in any section that has them, such as Wild animals in manual section 7 and the add-ons in wording section 8, so the agent can find them. The contents are built from the documents, not typed out.
- The agent reads a section with `read_section`. Its result is recorded as a `read` step, such as "Claims manual, section 9: Repeat claims", in place of the section's full text. The claim page lists these steps under "What the agent read".

### Instructions

Both are written from the policy wording and the manual. Neither comes from `data/evals/`, which stays unopened.

- `backend/instructions/claim.md` replaces the pilot's `backend/instructions.md`.
  - It follows the order of work in manual section 4.
  - It always reads the wording section for the claim's benefit, wording sections 9 and 10, and manual sections 2 (the decisions), 5 (documents), 6 (the payout) and 9 (repeat claims).
  - It reads other sections when the claim calls for them, such as the notes in manual section 7, story and documents disagreeing in section 8, and meals in section 10.
  - A decision's `section` can name a wording or a manual section.
- `backend/instructions/queue.md` tells the queue agent to:
  - list the claims and plan a to-do list of the claims it will work within its cap, oldest submission first unless it has a reason not to
  - hand each claim to `work_claim` and update the list after each one
  - put a claim that failed once back to To do and try it again later in the run
  - check for missed claims before it finishes
  - finish with a summary for the handlers: the decisions, what was paid and what is held, and what is left for them and why

### Running it

- `uv run -m agent` starts a run capped at the number of waiting claims. `uv run -m agent --cap 5` caps it at five. Each claim's line is printed as it comes back, then the summary.
- `uv run -m agent CLM-1001` works one claim with a claim agent and prints its line. It belongs to no run and has no to-do list, but a failure still puts the claim back in the queue or leaves it for a handler.
- The model is `deepseek/deepseek-v4.1-flash` with low reasoning effort, or `MODEL_NAME` if set, as in the pilot.
- The agent finds the backend at `UNDERCOVER_API`, which defaults to `http://127.0.0.1:8000`, the same as the dashboard's proxy. The pilot used `localhost`, which on a Mac can reach another server on port 8000.

### Dashboard

- **Queue page.** An "Agent run" panel above the tiles shows:
  - the run's id, its start time and its cap ("Up to 5 claims")
  - a state chip: Running in Marigold, Finished in Sea Green, Stopped in Coral
  - the to-do list in order, each item with a chip: To do in Cerulean, In progress in Marigold, Done in Sea Green, Left for a handler in Coral
  - the summary, once the run has finished

  It shows "No runs yet" before the first run and refreshes every two seconds. The tiles gain Needs a handler, in Raspberry with white text.
- **Claim page.**
  - A "What the agent read" panel lists the claim's `read` steps.
  - The step list shows `read` steps as "Read …" and `error` steps as "Failed: …".
  - The claim's facts show the number of failed attempts when there are any.
- **Instructions page.** Two panels: "Running the queue" and "Working a claim".

### End-to-end tests

These tests stand in for the agents by calling the API, as in the pilot, each on its own claims:

- a run: CLM-1005 and CLM-1006
- a failure: CLM-1007
- a section read: CLM-1008

The pilot's tests keep CLM-1001, CLM-1003, CLM-1020 and CLM-1025. Only the run test starts a run.

### How the criteria are checked

As in the pilot:

- API calls run against `npm run dev` on a freshly seeded database.
- Pages are checked in the browser with the Playwright MCP server at `http://localhost:5173`.
- Tests never call a model, and they run the retry middleware with no delay.
- Only criteria marked "Live" use the real model. Each live run starts from a reseeded database and works five claims at most.

## Phase 1: Runs and failures in the backend

Add the runs, the `needs_handler` state, failures, and the operations `start_run`, `get_latest_run`, `take_claim`, `update_todos`, `finish_run` and `fail_claim`, with the rules above. This phase is backend only.

- [x] pytest covers every rule for the six new operations, including each 404, 409 and 422
- [x] On a fresh database, `curl -s localhost:8000/api/runs/latest` prints `null`
- [x] `start_run` with cap 2 returns a run whose id starts `RUN-`, with status `running`, no to-do items, no claims and no summary, and `get_latest_run` then returns it
- [x] With cap 2, `take_claim` succeeds for CLM-1001 and CLM-1002, and CLM-1003 returns 409 with "has taken its cap of 2 claims"
- [x] With CLM-1001 back in waiting after a failure, `take_claim` for CLM-1001 succeeds in the same run
- [x] `take_claim` returns 409 for a claim that isn't waiting and for a finished run, and 404 for CLM-9999
- [x] `update_todos` with two items returns them in order, and `get_latest_run` shows them. A status of `maybe` returns 422
- [x] `fail_claim` on CLM-1001 in progress gives status `waiting`, `failures` 1 and an `error` step with the reason. Starting it and failing it again gives `needs_handler` and `failures` 2
- [x] `fail_claim` on a waiting claim returns 409, and so does `start_claim` on a claim that needs a handler
- [x] Nothing is decided or paid twice: after `record_decision`, `fail_claim` and a second `record_decision` both return 409, and a second `pay_claim` still returns 409
- [x] `finish_run` returns 409 naming CLM-1001 while it is back in waiting. With cap 3, two claims taken and another claim waiting, it returns 409 naming a waiting claim
- [x] Once a run owes nothing, `finish_run` returns `finished`, the summary and a finish time, and finishing again returns 409
- [x] With only two claims waiting in the queue and a cap of 3, finishing after both are decided succeeds
- [x] Starting a run while another is running marks the old one `stopped`, and its claim in progress goes back to `waiting` with `failures` 1 and an `error` step. A claim in progress that belongs to no run stays in progress
- [x] The OpenAPI test passes with the new operations
- [x] `npm run check` passes

## Phase 2: The claim agent looks things up

Seed the manual and split both documents into sections. Add `read_section`, the contents, and the instructions in two files, served by the new `get_instructions`. The claim agent gets `read_section` and the claim instructions, and records reads as `read` steps. The instructions page shows both parts. Update `docs/SPEC.md` so decisions follow the policy wording and the manual, and the manual leaves "Not for now".

- [x] `uv run -m backend.seed` prints the same line as before, and `grep -rn evals backend agent dashboard/src` finds nothing
- [x] `curl -s localhost:8000/api/documents/manual/sections/9` returns number 9, title `Repeat claims` and the section's text, which ends before section 10
- [x] `curl -s localhost:8000/api/documents/wording/sections/10` returns `How we work out your payment`. `manual/sections/15` and `handbook/sections/1` return 404
- [x] pytest: the 12 wording sections and 14 manual sections, joined in order, give back each document after its introduction
- [x] `curl -s localhost:8000/api/instructions` returns `queue` and `claim`
- [x] `claim` ends with the contents: 12 wording sections, 14 manual sections, and the 12 notes of manual section 7 from Unattended belongings to Treatment that can wait. It holds no section's text, such as "Count back 60 days"
- [x] A pytest test checks that the claim agent's tools are exactly `get_claim`, `get_policy`, `get_claim_history`, `read_section`, `record_decision` and `pay_claim`, each named after a backend operation
- [x] Stub model test: the system prompt the claim agent receives is `claim` from `get_instructions`
- [x] Stub model test: the stub reads manual section 9, and the claim's steps show the call to `read_section` and then a `read` step, "Claims manual, section 9: Repeat claims"
- [x] e2e: the instructions page shows "Running the queue" and "Working a claim"
- [x] Browser, `/instructions`: both parts, with no text box, input or edit button in the snapshot
- [x] `docs/SPEC.md` says decisions follow the policy wording and the claims manual, and no longer lists the manual under "Not for now"
- [x] `npm run check` passes

## Phase 3: A claim that fails is put right

Build `work_claim`'s core, which works one claim, records its steps, catches any failure with `fail_claim` and returns one line. Add the new default model, the timeout and `ModelRetryMiddleware`, and the backend address from `UNDERCOVER_API`. `uv run -m agent CLM-1001` uses it.

- [x] Stub model tests: deciding a claim returns `CLM-1001: approve $420.00, paid`, `CLM-1002: approve $1,350.00, waiting for sign-off` and `CLM-1003: refer $0.00`
- [x] Stub model test: a model that raises on every call leaves the claim `waiting` with `failures` 1 and an `error` step, and the line says "failed, back in the queue". A second run leaves it `needs_handler`, and the line says "failed twice, left for a handler"
- [x] Stub model test: an agent that ends without recording a decision is a failure, "ended without a decision"
- [x] Stub model test: a model that fails once and then answers is retried, and the claim is decided with `failures` 0
- [x] Stub model test: a tool whose backend call raises fails the claim, and it goes back in the queue
- [x] Stub model test: when the model fails after the decision is recorded, the claim keeps its decision, isn't put back, and the line gives the decision and the error
- [x] `model()` returns `deepseek/deepseek-v4.1-flash` with reasoning effort low, a 60-second timeout and no client retries, or `MODEL_NAME` if set
- [x] The agent reaches the backend at `UNDERCOVER_API`, or `http://127.0.0.1:8000` when it isn't set
- [x] Stub test of the command line: `uv run -m agent CLM-1001` prints the claim's line
- [x] Live: on a reseeded database with `npm run dev` running, `uv run -m agent CLM-1001` prints a line with a decision
- [x] Live: the steps of CLM-1001 include calls to `read_section` with their `read` steps, and no step holds the whole wording
- [x] `npm run check` passes

## Phase 4: The queue agent runs the queue

Build the queue agent with `list_claims`, `update_todos`, `work_claim` and `finish_run`, its instructions, the run id in runtime context, and `uv run -m agent` with `--cap`. The pilot's `work_queue()` gives way to it.

- [x] A pytest test checks that the queue agent's tools are exactly `list_claims`, `update_todos`, `work_claim` and `finish_run`, and that none of them takes a run id from the model
- [x] Stub model test, a whole run: with three claims waiting and cap 3, the queue stub writes the to-do list, works each claim, ticks each item off and finishes. The run is `finished` with the last list and the summary, and the command prints each claim's line and then the summary
- [x] Stub model test, the cap: with five claims waiting and cap 2, a third `work_claim` comes back to the stub as a refusal naming the cap, three claims stay `waiting`, and the run finishes
- [x] Stub model test, one failure doesn't stop the run: the claim agent fails on the first claim and the next claims are still worked
- [x] Stub model test, trying again: a claim that fails once is worked again later in the same run and decided, with `failures` 1
- [x] Stub model test, twice: a claim that fails twice needs a handler, its to-do item is Left for a handler, and the run finishes
- [x] Stub model test, missed claims: the stub calls `finish_run` with a claim still owed, the refusal names it, the stub works it, and the run then finishes
- [x] Stub test of the command line: `uv run -m agent --cap 5` starts a run with cap 5, and `uv run -m agent` starts one capped at the number of waiting claims
- [x] `npm run check` passes

## Phase 5: The dashboard shows the run

Add the run panel with the to-do list and the summary to the queue page, the Needs a handler state, "What the agent read", the `read` and `error` steps, and the failed attempts on the claim page.

- [x] vitest covers the run panel with no run, a running run with an item in each state, and a finished run with its summary. It also covers the Needs a handler tile and chip, "What the agent read", and the `read` and `error` steps
- [x] e2e, a run: the test starts a run with cap 2 and writes a to-do list for CLM-1005 and CLM-1006. Without a reload, the queue page shows the list, then each item changing as the test updates it, then the summary once the test decides both claims and finishes the run
- [x] e2e, a failure: the test starts and fails CLM-1007 twice. Its page shows Needs a handler, two failed attempts and both `error` steps, and the queue counts it under Needs a handler
- [x] e2e, a read: the test starts CLM-1008 and records a `read` step, and the claim page lists it under "What the agent read"
- [x] Browser, with `browser_evaluate`: each run state, to-do state and the Needs a handler chip has the background color from the design
- [x] Browser: screenshots of the queue page with a run, in light and dark mode, show rounded panels with no outlines, no one-edge borders and no gradients
- [x] Browser: `browser_console_messages` shows no errors on the queue, a claim and the instructions
- [x] `npm run check` passes

## Phase 6: A live run of five, and the documents

Run the harness live, capped at five, watch it in the dashboard, and bring the documents up to date.

- [x] Live: on a reseeded database, with `npm run dev` running and `/` open in the browser, `uv run -m agent --cap 5` prints five claim lines and a summary
- [x] Live, in the browser: snapshots taken during the run show the to-do list filling in and its items being ticked off
- [x] Live: afterwards no claim is `in_progress`, 20 claims are still `waiting`, and the run is `finished` with its summary
- [x] Live: each of the five claims shows its steps and "What the agent read", and each decision has a section and a reason of two or three sentences
- [x] Live: every approval over $1,000 is `waiting_for_sign_off` with no payment, every other approval is paid exactly its payout, and any failure shows as back in the queue or needing a handler
- [x] `docs/SPEC.md` lists the to-do list and the Needs a handler state in what the team sees
- [x] `docs/TECH_STACK.md` describes the two agents, the middleware, the default model, the entry points and `UNDERCOVER_API`
- [x] `docs/STATUS.md` describes what's built, how to run a capped run and one claim, and the live run
- [x] `npm run check` passes

## Not in this plan

- Scoring the agent against the handlers' decisions in `data/evals/`, which the process says not to open unless asked.
- Starting a run from the dashboard. Runs start from the command line, as in the pilot, and the dashboard shows them.
- Two runs at once. Starting a run stops an unfinished one.
- Handlers deciding a claim that needs a handler, or paying an approved claim that its agent left unpaid, from the dashboard. Such a claim keeps its decision, and its line in the run says so.
- Picking up a stopped run where it left off. Its claims go back in the queue for the next run.
