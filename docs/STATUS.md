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
    - The agents' instructions are in `backend/instructions/`, written from the wording and the manual: `queue.md` for running the queue and `claim.md` for working a claim.
    - `get_instructions` serves both, with the claim instructions followed by the contents of the wording and the manual.
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
  - A claim in full (`/claims/:claimId`): its policy and earlier claims, the decision and payment, what the agent read, and the agent's steps as it works, including reads and failures. Also the number of failed attempts, and a sign-off form for a held payout.
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

On November 3, 2026, after a reseed, `uv run -m agent --cap 5` with `deepseek/deepseek-v4.1-flash` worked five claims in 1 minute 8 seconds.

- The queue agent chose the oldest submissions: CLM-1001, CLM-1008, CLM-1011, CLM-1018 and CLM-1010.
- Its to-do list filled in, and each item was ticked off as the claim was worked.
- CLM-1001 was approved for $420.00 and paid.
- CLM-1008 ($2,240.00) and CLM-1011 ($1,150.00) were approved and wait for sign-off.
- CLM-1018 was referred for a missing proof of value, and CLM-1010 was declined under the alcohol exclusion.
- No claim failed, and the other 20 stayed waiting.
- Each claim agent read 10 or 11 sections of the wording and the manual, and every reason is three sentences.

The run before it found two problems, both fixed before this run:

- It finished with its last to-do item still In progress, so `finish_run` now refuses while an item is open.
- Two reasons ran to four sentences, so the claim instructions now say "never more" than three.

These decisions have not been scored against the handlers' decisions in `data/evals/`.
