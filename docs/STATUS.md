# Status

The claims pilot from `docs/PLAN.md` is built: all six phases are done. The fixes in `docs/PLAN_PILOT_FIXES.md` are built: all five phases are done.

## What's built

- `backend/`: FastAPI on SQLite.
  - The database is `backend/undercover.db`, or the file in `UNDERCOVER_DB`. `uv run -m backend.seed` rebuilds it from `data/` in place, and the backend seeds it on start when the file is missing.
  - Read operations: `health`, `list_claims`, `get_claim`, `get_policy`, `get_claim_history`, `list_handlers`, `get_policy_wording` and `get_instructions`. No route serves anyone's email, phone, date of birth or address: `get_claim_history` returns only a customer's earlier claims.
  - Decisions need reasons and a section, an approval needs a payout above $0.00, a start needs a thread id, and a step needs a title, a detail and a claim that has been started. Files are read as UTF-8.
  - Working a claim: `start_claim`, `add_step`, `list_steps`, `record_decision`, `pay_claim` and `sign_off_claim`. A claim goes from `waiting` to `in_progress`, then to `decided`, or to `waiting_for_sign_off` when an approval is over $1,000.00. `pay_claim` refuses a payout over $1,000.00 with 403 until a handler signs off, and signing off pays it. Each change takes the database's write lock before it checks the claim, so two requests can't both pass the same check.
- `agent/`: the UnderCover Agent on `create_agent`.
  - `run(claim_id, thread_id)` starts the claim, puts the instructions from `backend/instructions.md` and the policy wording in the system prompt, and records each tool use and each note that isn't blank as a step. The instructions are a numbered procedure whose every rule cites the policy wording.
  - Its five tools are `get_claim`, `get_policy`, `get_claim_history`, `record_decision` and `pay_claim`. Each makes one API call, accepts only well-formed ids, and gives the backend's refusals back to the model as plain sentences, including FastAPI's input errors.
  - The model makes one tool call at a time. It's `openai/gpt-6-luna` at low reasoning, or the model in `MODEL_NAME`.
- `dashboard/`: React on Vite, in UnderCover's brand, in light and dark mode.
  - The queue: a count of claims in each state and every claim's status and decision, refreshed every 2 seconds.
  - Each claim's page: the claim in full with its documents, the policy, the customer's earlier claims, the decision with its reasons and payment, and the agent's steps as they arrive. A claim waiting for sign-off has a choice of handler and a button to sign off and pay.
  - The instructions page: the agent's instructions and the policy wording, read only.
  - Every panel shows "Loading" or its error, so a failed load never reads as empty, and an error shows even after a page has loaded. A decline or referral shows no payout, a decision shows when it was recorded, and add-ons show their names from the policy wording.
- `e2e/`: Playwright tests of the queue, a claim, the agent's steps, sign-off and the instructions. They start their own backend on port 8001, with `e2e/undercover.db` reseeded on each `npm run e2e`, and their own dashboard on 5174, so they never touch the queue you use with `npm run dev`. Playwright's UI mode and the VS Code extension keep those servers running between runs, so restart them before running the tests again.

## Runs of the whole queue

**First run.** On October 25, 2026, `uv run -m agent` worked all 25 claims on GPT-6 Luna at low reasoning, in about 8 minutes. It approved 16 (13 paid, and 3 over $1,000.00 held for sign-off: CLM-1003, CLM-1008 and CLM-1011), declined 6 and referred 3, with none left waiting or in progress. CLM-1011 was then signed off in the dashboard and paid. Its accuracy against the handlers' decisions in `data/evals/` hasn't been measured. The queue was reseeded after that run.

**Second run, with the procedural prompt.** Later on October 25, 2026, `uv run -m agent` worked all 25 claims in 4 minutes 54 seconds, against the first run's 8 minutes, although the model now makes one tool call at a time. It approved 17, declined 5 and referred 3, with none left waiting or in progress. Of the approvals, 13 were paid, 3 were held for sign-off (CLM-1003 at $3,750, CLM-1008 at $2,240 and CLM-1011 at $1,330), and CLM-1024 was approved at $0.00. For CLM-1024, the claim history showed $250 already paid for the same phone, so nothing was left to pay. Every claim was read first, and its policy and history were read with its own ids. These decisions haven't been scored either. After this run, an approval must have a payout above $0.00, and the queue was reseeded.

**Third run, once an approval must pay something.** On October 26, 2026, with the prompt's three changes from phase 5 of the fixes, `uv run -m agent` worked all 25 claims in 16 minutes 33 seconds. Each claim took five or six steps, as in the second run, so the extra time was the model's response time. Even the step from reading a claim to reading its policy, which needs no working out, took 2 to 4 seconds at the start and end of the run and 7 to 11 seconds in the middle. So two runs can't tell how much of the second run's speed came from its prompt.

It approved 16, declined 6 and referred 3, with none left waiting or in progress. Of the approvals, 13 were paid and 3 were held for sign-off (CLM-1003 at $3,750, CLM-1008 at $2,240 and CLM-1011 at $1,150). Every approval of $1,000.00 or less was paid.

Three decisions differ from the second run:

- **CLM-1024** was declined, because the earlier payment for the same phone left nothing to pay.
- **CLM-1011** fell from $1,330 to $1,150. The agent counted the suit, and the camera with its lens, as one item each, as section 5 says.
- **CLM-1021** rose from $825 to $954. The agent gave the headphones the Electronics Plus limit, though section 8's list of electronics doesn't include headphones.

Every claim was read first, and its policy and history were read with its own ids. These decisions are in the database now, and they haven't been scored.

## How to run it

- `npm run dev` starts the backend on port 8000 and the dashboard at `http://localhost:5173`.
- With the backend running, `uv run -m agent` works every waiting claim, and `uv run -m agent CLM-1001` works just that one.
- `uv run -m backend.seed` resets the database from `data/`.
- `npm run check` runs every check.
