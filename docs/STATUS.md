# Status

The claims pilot, built in phases from `docs/PLAN.md`. Phase 1 of 6 is done.

## What's built

- `backend/`: FastAPI on SQLite. `uv run -m backend.seed` rebuilds the database (`backend/undercover.db`, or the file in `UNDERCOVER_DB`) from `data/`, and the backend seeds it on start when the file is missing. The read operations are `list_claims`, `get_claim`, `get_policy`, `get_customer`, `list_handlers` and `get_policy_wording`, alongside `health`.
- `agent/`: still the skeleton, the entry point `run(claim_id, thread_id)` with one tool that calls the health route.
- `dashboard/`: still the skeleton, one page that shows whether the backend is up.
- `e2e/`: one test of that page.

## How to run it

- `npm run dev` starts the backend on port 8000 and the dashboard on 5173.
- `uv run -m backend.seed` resets the database from `data/`.
- `npm run check` runs every check.
