# Status

The claims pilot in `docs/PLAN.md` and the harness in `docs/PLAN_HARNESS.md` are built: all six phases of each are done.

## Running it

- `npm run dev` starts the backend on port 8000 and the dashboard on http://localhost:5173.
- `uv run -m backend.seed` rebuilds the database from `data/`, putting every claim back in the queue.
- `uv run -m agent --cap 5` starts a run of the queue agent that can take up to five claims. `uv run -m agent` caps the run at the number of waiting claims. A run prints each claim's line as it comes back, then the run's summary, or says no claims are waiting. Watch its to-do list on the queue page.
- `uv run -m agent CLM-1001` works one claim with a fresh claim agent, outside any run, and prints one line, like `CLM-1001: approve $420.00, paid`.
- Both use the real model through OpenRouter: DeepSeek V4.1 Flash by default, or `MODEL_NAME`. For a trial, reseed first and cap the run at five claims.

## Built

- `backend/`: SQLite database seeded from `data/` (never `data/evals/`), at `undercover.db` or the path in `UNDERCOVER_DB`, created on startup when missing.
  - Read operations: `health`, `list_claims`, `get_claim`, `get_policy`, `get_claim_history`, `list_handlers`, `list_steps`, `get_instructions`, `read_section` and `get_latest_run`.
  - Workflow operations: `start_claim`, `record_step`, `record_decision`, `pay_claim`, `sign_off_claim` and `fail_claim`.
  - Run operations: `start_run`, `take_claim`, `update_todos` and `finish_run`.
  - Claims and payments:
    - A claim moves from waiting to in progress to decided, or to waiting for sign-off when an approval pays over the limit in `company.json`.
    - `pay_claim` refuses such a payout with a 403 until a handler signs off, and signing off pays it.
    - A claim that fails goes back to waiting, and the second time to `needs_handler`. Only a claim in progress can fail, so nothing is decided twice.
  - Runs:
    - A run has a cap on the claims it can take, and a to-do list.
    - It can't finish while it has missed a waiting claim within its cap, or while a to-do item is still To do or In progress.
    - Starting a run stops any run left unfinished and puts its claims in progress back in the queue.
  - The documents and the instructions:
    - Seeding stores the policy wording and the claims manual, and `read_section` serves one numbered section of either.
    - The agents' instructions are in `backend/instructions/`, written from the wording and the manual as goal, tools and rules: `queue.md` for running the queue and `claim.md` for working a claim.
    - `get_instructions` serves both. The claim instructions are followed by the sections every claim needs, in full (wording 1, 9, 10 and 11, manual 2, 3, 5, 6 and 9), then the contents of both documents. The list of those sections is `GIVEN` in `backend/documents.py`.
  - Each request that writes takes SQLite's write lock first (`BEGIN IMMEDIATE`), so a check and its write can't interleave with another request's, and the guarantees hold when requests arrive at once.
  - A test checks that every operation follows the API rules.
- `agent/main.py`: the claim agent.
  - `work_claim(claim_id)` starts the claim and works it with a fresh claim agent, using six tools named after backend operations: `get_claim`, `get_policy`, `get_claim_history`, `read_section`, `record_decision` and `pay_claim`.
  - It records every tool call, tool result and message as a step, and each section read as a `read` step, then reports on the claim in one line.
  - If anything fails, or the agent ends without a decision, it records the failure with `fail_claim`, so the claim is never left in progress. A claim that fails after its decision keeps the decision.
  - The model is `deepseek/deepseek-v4.1-flash` at low reasoning effort, or `MODEL_NAME`. A model call times out after 60 seconds, and `ModelRetryMiddleware` retries it twice.
  - A claim agent can take 60 LangGraph steps.
  - The agents reach the backend at `UNDERCOVER_API`, or `http://127.0.0.1:8000`.
- `agent/queue.py`: the queue agent.
  - `run_queue(cap)` starts a run and gives the queue agent four tools: `list_claims`, `update_todos`, `work_claim` and `finish_run`.
  - `work_claim` takes the claim into the run, within its cap, then hands it to a fresh claim agent and returns its one-line report.
  - The run id reaches the tools through LangChain's runtime context, never from the model.
  - A run gets 20 LangGraph steps for each claim it can take.
- `dashboard/`:
  - The queue (`/`): the latest agent run with its to-do list and summary, counts by state, including Needs a handler, and a line per claim.
  - A claim in full (`/claims/:claimId`): its policy and earlier claims, the decision and payment, what the agent read, and the agent's steps as it works, including reads and failures. "What the agent read" lists the sections it looked up for the claim, beyond those every claim starts with. Also the number of failed attempts, and a sign-off form for a held payout.
  - The agent's instructions (`/instructions`), in two parts, running the queue and working a claim, read only.
  - The queue and a claim page refresh every two seconds. Styled to `BRAND.md` in light and dark mode.
- `e2e/`: tests of:
  - the three pages
  - the agent's steps appearing on a claim page
  - a handler signing off a held payout
  - the queue page following a run's to-do list to its summary
  - a claim that fails twice
  - what the agent read

  Playwright runs its own backend on port 8001 with `e2e/undercover.db`, and its own dashboard on port 5174, so it can run next to `npm run dev`.

## Last live run

On November 3, 2026, after the human review, a reseeded `uv run -m agent --cap 5` with `deepseek/deepseek-v4.1-flash` worked five claims in 27 seconds.

- The queue agent handed out all five claims at once.
- CLM-1001 was approved for $420.00 and paid, and CLM-1010 was declined.
- CLM-1008 ($2,240.00) and CLM-1011 ($1,150.00) were approved and wait for sign-off. CLM-1018 was referred.
- These are the same decisions as the three runs before it.
- Each claim agent looked up two or three sections for its claim, such as the benefit's wording section and the notes in manual section 7.
- Every reason is three sentences, and the to-do list ended with each item Done or Left for a handler.

These decisions have not been scored against the handlers' decisions in `data/evals/`.

## Human review

A person reviewed the harness after the build (`docs/HUMAN_REVIEW_HARNESS.md`). Its points on the backend address, the backend calls, the imports and `run_queue` were confirmed, and kept.

1. **The instructions were scripted procedures.** Confirmed, and decided: goal and tools.
   - The brief wants the agent to organize its own work. The backend now holds the cap, missed claims, open to-do items and failures, so the queue instructions give the goal, the tools and what the handlers rely on.
   - The claim agent is given the sections every claim needs up front, and looks up only what its claim calls for.
   - The first goal-only run kept every item In progress until the end, and called payouts waiting for sign-off Done. The instructions now say why the list must stay true (the handlers watch it live) and what Done and Left for a handler mean.
2. **An approval of $0.00 was said to be a prompt rule only.** Not confirmed. The backend has refused it since the pilot (`backend/models.py`, tested in `test_workflow.py`), so nothing changed.
3. **A new HTTP client for every backend call.** Kept.
   - Opening a connection to the local backend costs very little next to a model call of several seconds.
   - It keeps `request()` simple, and lets the tests swap in the test backend.
   - The backend does the same with a new SQLite connection per request, which is also kept.
4. **Found by looking for the same patterns elsewhere.** The cap held only while the queue agent followed its instruction to hand out one claim at a time. Eight `take_claim` calls sent at once went over a cap of 1 in 14 of 20 tries, and a claim could be started twice. Each write request now takes the write lock first, with tests. This mattered at once: given goal and tools, the agent chose to work claims in parallel.

Deferred:

- A run of the whole queue could hand out every waiting claim at once. Five at once is tested live, but twenty is not. If it strains OpenRouter or SQLite, LangGraph's `max_concurrency` can bound it.
- `docs/PLAN_HARNESS.md` still describes the procedural instructions, as the record of the plan that was built.
