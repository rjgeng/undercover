# Status

The claims pilot from `docs/PLAN.md` is built: all six phases are done. The fixes in `docs/PLAN_PILOT_FIXES.md` are under way: phases 1 and 2 of 4 are done.

## What's built

- `backend/`: FastAPI on SQLite.
  - The database is `backend/undercover.db`, or the file in `UNDERCOVER_DB`. `uv run -m backend.seed` rebuilds it from `data/` in place, and the backend seeds it on start when the file is missing.
  - Read operations: `health`, `list_claims`, `get_claim`, `get_policy`, `get_claim_history`, `list_handlers`, `get_policy_wording` and `get_instructions`. No route serves anyone's email, phone, date of birth or address: `get_claim_history` returns only a customer's earlier claims.
  - Decisions need reasons and a section, a start needs a thread id, and a step needs a title, a detail and a claim that has been started. Files are read as UTF-8.
  - Working a claim: `start_claim`, `add_step`, `list_steps`, `record_decision`, `pay_claim` and `sign_off_claim`. A claim goes from `waiting` to `in_progress`, then to `decided`, or to `waiting_for_sign_off` when an approval is over $1,000.00. `pay_claim` refuses a payout over $1,000.00 with 403 until a handler signs off, and signing off pays it. Each change takes the database's write lock before it checks the claim, so two requests can't both pass the same check.
- `agent/`: the UnderCover Agent on `create_agent`.
  - `run(claim_id, thread_id)` starts the claim, puts the instructions from `backend/instructions.md` and the policy wording in the system prompt, and records each tool use and each note as a step.
  - Its five tools are `get_claim`, `get_policy`, `get_claim_history`, `record_decision` and `pay_claim`. Each makes one API call, accepts only well-formed ids, and gives the backend's refusals back to the model as plain sentences, including FastAPI's input errors.
  - The model makes one tool call at a time. It's `openai/gpt-6-luna` at low reasoning, or the model in `MODEL_NAME`.
- `dashboard/`: React on Vite, in UnderCover's brand, in light and dark mode.
  - The queue: a count of claims in each state and every claim's status and decision, refreshed every 2 seconds.
  - Each claim's page: the claim in full with its documents, the policy, the customer's earlier claims, the decision with its reasons and payment, and the agent's steps as they arrive. A claim waiting for sign-off has a choice of handler and a button to sign off and pay.
  - The instructions page: the agent's instructions and the policy wording, read only.
- `e2e/`: Playwright tests of the queue, a claim, the agent's steps, sign-off and the instructions. They start their own backend on port 8001, with `e2e/undercover.db` reseeded on each `npm run e2e`, and their own dashboard on 5174, so they never touch the queue you use with `npm run dev`. Playwright's UI mode and the VS Code extension keep those servers running between runs, so restart them before running the tests again.

## The first run of the whole queue

On October 25, 2026, `uv run -m agent` worked all 25 claims on GPT-6 Luna at low reasoning, in about 8 minutes. It approved 16 (13 paid, and 3 over $1,000.00 held for sign-off: CLM-1003, CLM-1008 and CLM-1011), declined 6 and referred 3, with none left waiting or in progress. CLM-1011 was then signed off in the dashboard and paid. Its accuracy against the handlers' decisions in `data/evals/` hasn't been measured. The queue has been reseeded since that run.

## How to run it

- `npm run dev` starts the backend on port 8000 and the dashboard at `http://localhost:5173`.
- With the backend running, `uv run -m agent` works every waiting claim, and `uv run -m agent CLM-1001` works just that one.
- `uv run -m backend.seed` resets the database from `data/`.
- `npm run check` runs every check.
