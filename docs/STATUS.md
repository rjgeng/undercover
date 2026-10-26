# Status

The claims pilot, built in phases from `docs/PLAN.md`. Phases 1 to 4 of 6 are done.

## What's built

- `backend/`: FastAPI on SQLite. `uv run -m backend.seed` rebuilds the database (`backend/undercover.db`, or the file in `UNDERCOVER_DB`) from `data/`, and the backend seeds it on start when the file is missing. The read operations are `list_claims`, `get_claim`, `get_policy`, `get_customer`, `list_handlers` and `get_policy_wording`, alongside `health`.
- Working a claim: `start_claim`, `add_step`, `list_steps`, `record_decision`, `pay_claim` and `sign_off_claim`. A claim goes from `waiting` to `in_progress` to `decided`, or to `waiting_for_sign_off` when an approval is over $1,000.00. `pay_claim` refuses a payout over $1,000.00 with 403 until a handler signs off, and signing off pays it.
- `get_instructions` serves the agent's instructions from `backend/instructions.md`.
- `agent/`: the UnderCover Agent on `create_agent`. `run(claim_id, thread_id)` starts the claim, puts the instructions and the policy wording in the system prompt, and records each tool use and note as a step. Its five tools (`get_claim`, `get_policy`, `get_claim_history`, `record_decision`, `pay_claim`) each make one API call and give the backend's refusals back to the model as text. The model is `openai/gpt-6-luna` at low reasoning, or `MODEL_NAME`.
- `dashboard/`: React on Vite in UnderCover's brand, light and dark. The queue page counts the claims in each state and lists every claim, refreshing every 2 seconds.
- `e2e/`: Playwright tests of the queue. They start their own backend on port 8001, with the database `e2e/undercover.db` reseeded each run, and their own dashboard on 5174, so they never touch the queue you use with `npm run dev`.

## How to run it

- `npm run dev` starts the backend on port 8000 and the dashboard on 5173.
- `uv run -m agent` works every waiting claim, and `uv run -m agent CLM-1001` works just that one. The backend must be running.
- `uv run -m backend.seed` resets the database from `data/`.
- `npm run check` runs every check.
