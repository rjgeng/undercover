# Plan: the claims pilot

This plan builds the pilot in `docs/SPEC.md`. It has three parts. The backend holds UnderCover's records and enforces the rules. The UnderCover Agent works the queue through the backend's API. On the dashboard the claims team watches the queue, reads each claim and its decision, follows the agent step by step, reads the agent's instructions and signs off payouts over $1,000.

There are six phases. Each one ends with every check green, its criteria ticked, `docs/STATUS.md` updated and a commit.

## How it fits together

```
dashboard (React, :5173) ──/api──▶ backend (FastAPI, :8000) ──▶ SQLite (backend/undercover.db)
                                        ▲                                ▲
UnderCover Agent (uv run -m agent) ─────┘ HTTP only                      └── seeded from data/
```

### Decisions and why

1. **SQLite through Python's built-in `sqlite3`, with no ORM.** There are only a handful of tables, and plain SQL with parameters is the simplest thing that works. Each record from `data/` is stored whole as JSON text, beside the columns for a claim's state, because nothing queries inside the records. Each request opens its own short-lived connection to the file named by `UNDERCOVER_DB`, which defaults to `backend/undercover.db`; git already ignores `*.db`. Every statement is fixed SQL with `?` parameters and is never built from strings, which ruff's S608 rule would flag.
2. **The backend starts from the files in `data/`.** `uv run -m backend.seed` loads `data/claims.json`, `policies.json`, `customers.json` and `handlers.json`. It drops and recreates the tables in one transaction and never deletes the file, so it's safe to run while the backend is up, on Windows too. The backend seeds itself on start when the file is missing. The seed names each file it reads, so it never touches `data/evals/`, `data/security/`, `knowledge.json` or the claims manual. The claims marked `open` in the data start as `waiting`. The policy wording and the $1,000 limit are reference data, so the backend reads them from `data/policy_wording.md` and `data/company.json` rather than copying them into tables.
3. **The backend owns each claim's state, and the $1,000 rule lives in the payment operation, not in the prompt.** A model can ignore its instructions, so the backend refuses any payment over the limit that a handler hasn't signed off, whoever asks. The states are the four in the spec:

   | From | Operation | To |
   |---|---|---|
   | `waiting` | `start_claim` | `in_progress` |
   | `in_progress` | `record_decision`: decline or refer | `decided` |
   | `in_progress` | `record_decision`: approve, payout up to $1,000.00 | `decided`, then the agent pays with `pay_claim` |
   | `in_progress` | `record_decision`: approve, payout over $1,000.00 | `waiting_for_sign_off` |
   | `waiting_for_sign_off` | `sign_off_claim` by a handler | `decided`, and paid |

   - **Decisions:** a decision is final, so a second one gets 409. A referral is a decision, so a referred claim is `decided` with the decision `refer`.
   - **Amounts:** payouts and amounts are rounded to cents. A payout can't be negative, and a decline or referral must have a payout of zero (422 otherwise). An approval of $0.00 is allowed, since the deductible can leave nothing to pay. Exactly $1,000.00 needs no sign-off.
   - **Paying:** `pay_claim` takes the amount. An approved claim over the limit that isn't signed off always gets 403, whatever the amount. Otherwise it gets 409 when the claim isn't approved, when the amount isn't the approved payout, or when it's already paid.
   - **Signing off:** sign-off needs a handler on record whose `can_approve_over_limit` is true (403 otherwise). It records who signed off and when, then pays the payout.
   - Payments are only recorded, never made.
4. **The harness does the fixed steps in code, and the model makes the judgment.** `run(claim_id, thread_id)` starts the claim and fetches the instructions and the policy wording through the API. It puts both in the system prompt, so the wording is in front of every decision. The model gets five tools, each one API call: `get_claim`, `get_policy`, `get_claim_history`, `record_decision` and `pay_claim`. It has no tool for signing off and no way to reach anything but the API. `get_claim_history` returns only the earlier claims on the customer's record, not their contact details, since the agent doesn't need personal data.
5. **The harness records the steps as the agent works.** `run` streams the agent's updates and posts a step to the backend for each tool use when its result comes back. Each step has a fixed plain title ("Read the claim", "Read the policy", "Read the claim history", "Record the decision", "Pay the claim"), and its detail holds what went in and what came back. Any text the model writes becomes a step titled "Note". The dashboard polls every 2 seconds, which is the simplest way to show progress live, with no websockets.
6. **Refusals go back to the model as text.** A tool that raises an error ends the whole run and leaves the claim in progress. So all five tools call the API through one small helper that returns the backend's message as the tool's result on any 4xx response, and raises on anything else. A refused payment comes back as "A payout over $1,000.00 needs a handler's sign-off.", and a referral sent with a payout comes back as a 422 the model can correct.
7. **The instructions live in the backend** as `backend/instructions.md`, served read only by `get_instructions`. The agent and the dashboard both read them from there.
8. **The dashboard uses plain `fetch` and hash routes** (`#/`, `#/claims/CLM-1001`, `#/instructions`), so it needs no router library. The types for the API's records live in one file, and each claim id in the queue is a link to its page.
9. **The end-to-end tests run on their own database and ports**, so they never touch the queue you use with `npm run dev`:
   - **Servers:** the backend runs on 8001 with `e2e/undercover.db`, reseeded each run, and the dashboard runs on 5174. Playwright passes their settings through each web server's `env` option rather than on the command line, so it works on Windows, and doesn't reuse a server that's already running.
   - **Claims:** each test that changes a claim works on a claim of its own: CLM-1002 for sign-off, CLM-1004 for steps and CLM-1005 for the queue refreshing. The other tests only read, so the order the tests run in doesn't matter.

### The API

Every operation has an `operation_id`, a one-line docstring and no optional inputs, and a test checks this for every route.

| `operation_id` | Method and path | Inputs | Used by |
|---|---|---|---|
| `health` | `GET /api/health` | | already built |
| `list_claims` | `GET /api/claims` | | dashboard, agent's command line |
| `get_claim` | `GET /api/claims/{claim_id}` | | dashboard, agent tool |
| `get_policy` | `GET /api/policies/{policy_id}` | | dashboard, agent tool |
| `get_customer` | `GET /api/customers/{customer_id}` | | dashboard, agent tool (earlier claims only) |
| `list_handlers` | `GET /api/handlers` | | dashboard |
| `get_policy_wording` | `GET /api/policy-wording` | | agent harness, dashboard |
| `get_instructions` | `GET /api/instructions` | | agent harness, dashboard |
| `start_claim` | `POST /api/claims/{claim_id}/start` | `thread_id` | agent harness |
| `add_step` | `POST /api/claims/{claim_id}/steps` | `kind` (`tool` or `note`), `title`, `detail` | agent harness |
| `list_steps` | `GET /api/claims/{claim_id}/steps` | | dashboard |
| `record_decision` | `POST /api/claims/{claim_id}/decision` | `decision`, `payout`, `reasons`, `policy_section` | agent tool |
| `pay_claim` | `POST /api/claims/{claim_id}/payment` | `amount` | agent tool |
| `sign_off_claim` | `POST /api/claims/{claim_id}/sign-off` | `handler_id` | dashboard |

- **`list_claims`** returns each claim's id, customer name, type, summary, amount claimed, submission date, status, decision and payout.
- **`get_claim`** returns the whole claim with its decision, reasons, policy section, thread id, sign-off and payment.
- **Missing records** get 404 with a plain message, such as "Claim CLM-9999 not found".

## Phase 1: The records and the read API

**Builds:**

- The SQLite schema, `uv run -m backend.seed`, and seeding on start when the database is missing.
- The read operations `list_claims`, `get_claim`, `get_policy`, `get_customer`, `list_handlers` and `get_policy_wording`, with Pydantic response models.
- Tests that run on a temporary database, seeded in a fixture.

**Why first:** everything else reads these records, and this phase settles where the data comes from before anything changes it.

- [x] `uv run -m backend.seed` prints `Seeded 25 claims, 50 policies, 49 customers and 3 handlers.`
- [x] With the backend running, `curl -s localhost:8000/api/claims` returns 25 claims, CLM-1001 to CLM-1025, each with status `waiting`.
- [x] `curl -s localhost:8000/api/claims/CLM-1001` returns 3 items, 4 documents, `amount_claimed` 420.0, customer CUS-3001 and no decision.
- [x] `curl -s -w '\n%{http_code}\n' localhost:8000/api/claims/CLM-9999` prints the detail `Claim CLM-9999 not found` and the status 404.
- [x] `curl -s localhost:8000/api/policies/POL-2001` returns the `premium` plan with a trip to Rome, Italy.
- [x] `curl -s localhost:8000/api/customers/CUS-3001` returns Maya Patel with one earlier claim, CLM-0412.
- [x] `curl -s localhost:8000/api/policy-wording` returns version `2026.1` and text that starts with `# UnderCover Travel Insurance: Policy Wording`.
- [x] `curl -s localhost:8000/api/handlers` returns the three handlers.
- [x] With the backend stopped, deleting `backend/undercover.db` and starting the backend again seeds a fresh database.
- [x] A test walks the app's routes and checks that each one sets its own `operation_id`, has a one-line description and takes only required inputs.
- [x] `grep -rnE "evals|claims_manual|knowledge|security" backend agent` finds nothing.
- [x] `npm run check` passes, with Python coverage at 80% or more.

## Phase 2: Working a claim: states, steps, decisions, payment and sign-off

**Builds:** the operations `start_claim`, `add_step`, `list_steps`, `record_decision`, `pay_claim` and `sign_off_claim`, with the states and rules in decision 3. The limit comes from `payout_approval_limit` in `data/company.json`.

**Why now:** this is where the spec's one hard rule lives, so it's built and tested on its own, before any model is involved.

- [x] Tests cover every row of the state table and every refusal:
  - starting a claim that isn't waiting (409)
  - a decision on a claim that isn't in progress (409)
  - a negative payout (422)
  - a decline or referral with a payout above zero (422)
  - paying a claim that isn't approved (409)
  - paying an approved claim over the limit that isn't signed off, with its payout and with a smaller amount (403 both times)
  - paying a different amount from the payout (409)
  - paying twice (409)
  - signing off a claim that isn't waiting for sign-off (409)
  - signing off with an unknown handler (404)
  - signing off with a handler who can't approve over the limit, added to the test database (403)
- [x] Tests at the limit: approving 1000.00 ends `decided` and can be paid, approving 1000.01 ends `waiting_for_sign_off`, and an amount like 420.004 is stored as 420.0.
- [x] On the running backend, `start_claim` on CLM-1002 with a thread id returns status `in_progress`.
- [x] `record_decision` on CLM-1002 with `approve` and a payout of 1150.0 returns status `waiting_for_sign_off`.
- [x] `pay_claim` on CLM-1002 with 1150.0, through `curl -s -w '\n%{http_code}\n'`, prints `A payout over $1,000.00 needs a handler's sign-off.` and 403, and `get_claim` still shows no payment.
- [x] `sign_off_claim` on CLM-1002 with HND-01 returns status `decided`, signed off by HND-01, paid 1150.0.
- [x] On CLM-1001, approving 420.0 returns `decided`, and `pay_claim` with 420.0 succeeds and records the payment.
- [x] Two `add_step` calls on CLM-1001 come back from `list_steps` in the order they were posted.
- [x] With the backend still running, `uv run -m backend.seed`, then `curl -s localhost:8000/api/claims`, shows 25 `waiting` claims again.
- [x] `npm run check` passes.

## Phase 3: The UnderCover Agent

**Builds:**

- **The instructions:** `backend/instructions.md`, served by `get_instructions`. They state the goal rather than spelling out every step:
  - Decide the claim as a handler would, from the claim, the policy, the claim history and the policy wording.
  - Approve, decline or refer, and refer when the claim needs a person's judgment or more information, such as a missing document.
  - Work out the payout as section 10 of the wording sets out.
  - Record the decision with two or three sentences of explanation and the relevant section.
  - Pay an approved payout, except that a payout over $1,000 waits for a handler's sign-off.

  They don't mention the claims manual.
- **The agent:** the five tools in `agent/main.py`, with the helper from decision 6, and `run(claim_id, thread_id)`, which replaces the hello-world tool. The model stays as it is: `openai/gpt-6-luna` at low reasoning, or the model in `MODEL_NAME`.
- **The command line:** `agent/__main__.py`. `uv run -m agent` works every waiting claim in turn, each on a new thread id, and `uv run -m agent CLM-1001 CLM-1004` works just those claims. It prints a line per claim:
  - `CLM-1001: approve $420.00 (decided, paid)`
  - `CLM-1002: approve $1,150.00 (waiting for sign-off)`
  - `CLM-1007: no decision (in progress)` when the model stops without recording one, and the command line moves on to the next claim
  - a claim that isn't waiting is skipped with where it stands, such as `CLM-1003: skipped, it's decided`
- **Tests** with a stub model, against the backend on a temporary database.

**Why:** the harness keeps the parts that must always happen in code: starting the claim, loading the wording and recording steps. It leaves the decision to the model, through tools that can only go through the API.

- [x] A stub-model test on CLM-1001 reads the claim, the policy and the history, approves 420.0 and pays it. The claim ends `decided` and paid, with the steps "Read the claim", "Read the policy", "Read the claim history", "Record the decision" and "Pay the claim" in that order.
- [x] A stub-model test approves 1150.0 on CLM-1002 and then tries to pay. It gets the refusal back as the tool result, and the claim ends `waiting_for_sign_off` with no payment.
- [x] A stub-model test refers CLM-1001 with a payout of 50.0 and gets the 422 message back as the tool result. It then refers it with a payout of zero, and the claim ends `decided`.
- [x] A stub-model test of a decline ends `decided` with a payout of zero and no payment.
- [x] Tests of the command line cover working the queue, working named claims, skipping a claim that isn't waiting, and a claim left with no decision.
- [x] `curl -s localhost:8000/api/instructions` returns the instructions, and they don't mention the claims manual.
- [x] A live run, `uv run -m agent CLM-1001`, prints a decision line. It's one claim on the real model and costs well under a cent. Then:
  - `get_claim` shows a decision, reasons of two or three sentences and a policy section.
  - If the decision is an approval of $1,000.00 or less, `get_claim` shows a payment equal to the payout.
  - `list_steps` shows "Read the claim", "Read the policy" and "Read the claim history" before "Record the decision".
  - `uv run -m backend.seed` resets the queue afterwards.
- [x] `npm run check` passes.

## Phase 4: The dashboard and the queue

**Builds:**

- **The brand, following `docs/BRAND.md` in full:**
  - Instrument Sans for text and JetBrains Mono for numbers and ids, from Google Fonts. Instrument Serif is for a tagline or a quote, and the pilot has neither.
  - The colors as CSS variables, with Midnight ink on light backgrounds and Sea Mist on dark ones.
  - Light and dark mode from the system setting: `#F0F4F5` behind white panels, and `#04232E` behind black ones.
  - Rounded panels with no outline, no border on one edge, no line across the top of the page and no gradients.
  - The four states sit side by side, so they get the four colors in brand order: Cerulean for waiting, Marigold for in progress, Coral for waiting for sign-off and Sea Green for decided. Each uses the text color the brand gives it.
- **The plumbing:** the API types and fetch functions; helpers for money (`$1,250.00`), dates and labels; and the hash routes, with a header to move between the queue and the instructions.
- **The queue page:**
  - a count of claims in each state
  - a table of every claim with its id as a link, the customer, the type, the summary, the amount claimed, the submission date and the status, plus the decision and payout once there is one
  - a refresh every 2 seconds
- **The end-to-end setup from decision 9:**
  - In `playwright.config.ts`, the backend's command is `uv run -m backend.seed && uv run -m uvicorn backend.main:app --port 8001`, with `env: { UNDERCOVER_DB: "e2e/undercover.db" }`.
  - The dashboard runs on 5174 with `env: { BACKEND_URL: "http://127.0.0.1:8001" }`, and the base URL moves to 5174.
  - Both servers have `reuseExistingServer: false`.
  - `dashboard/vite.config.ts` takes the proxy's target from `BACKEND_URL`, defaulting to 8000.
  - The queue test replaces the skeleton's health test, since the health message leaves the page.

**Why:** the queue is the screen the team works from, and it sets the look and the plumbing the other pages reuse.

- [x] Vitest tests cover the queue's counts and rows from a stubbed API, each state's label, money and date formatting, and the routes.
- [x] An end-to-end test opens the queue and sees 25 claims, a count for each of the four states adding up to 25, and CLM-1001 with $420.00 and Waiting.
- [x] An end-to-end test opens the queue, starts CLM-1005 through the API, and sees its row change to In progress within 3 seconds without a reload.
- [x] With `npm run dev` running, localhost:5173 is checked in the browser through the Playwright MCP server, in light and dark mode:
  - the queue is in Instrument Sans, with numbers and ids in JetBrains Mono
  - the page background is `#F0F4F5` in light mode and `#04232E` in dark mode, with white and black panels and Midnight and Sea Mist ink
  - no panel or header has an outline or a one-edge border, and there's no line across the top
- [x] With the queue open in the browser, `start_claim` on CLM-1001 is called through curl, and a later snapshot, taken without a reload, shows CLM-1001 as In progress. `uv run -m backend.seed` resets it afterwards.
- [x] `npm run check` passes, with TypeScript coverage at 80% or more.

The Playwright MCP server couldn't start here, because it needs Google Chrome and Chrome isn't installed, so the browser checks in this phase and the next ran in the repo's own Playwright with its Chromium: light and dark mode, the computed fonts and colors, and screenshots.

## Phase 5: The claim page, the agent's steps, sign-off and the instructions

**Builds:**

- **The claim page:**
  - the claim in full: type, submission date, amount claimed, summary, story, incident date and place, the items with their amounts, and each document's name, type and text
  - the policy: plan, add-ons, purchase date, trip and travelers
  - the customer and their earlier claims
  - the decision, with its payout, reasons, policy section, sign-off and payment
- **The agent's steps:** in order and refreshed every 2 seconds, each with its title and an expandable detail.
- **Sign-off:** while a claim waits for sign-off, a choice of handler and a "Sign off and pay $1,150.00" button. After sign-off the page shows who signed off and the payment.
- **The instructions page:** the agent's instructions as read-only text, with the policy wording the agent reads alongside them.
- **A missing claim:** a plain message for a claim id that doesn't exist.

**Why:** this is where a handler checks the agent's work and takes the one action the pilot gives them, signing off.

- [ ] Vitest tests cover the claim page in each state, the steps, the sign-off request, the instructions page and the missing-claim message.
- [ ] An end-to-end test opens CLM-1001 and sees:
  - its story, its three items and its four documents, including the text "Flight MA 611"
  - the Premium plan
  - the earlier claim CLM-0412
- [ ] An end-to-end test opens CLM-1004, starts it through the API, posts two steps, and sees both appear in order without a reload.
- [ ] An end-to-end test plays the agent on CLM-1002 through the API: it starts the claim, approves 1150.0, then tries to pay and gets 403. On the page it sees Waiting for sign-off, picks Dana Whitfield and clicks Sign off. It then sees Decided, signed off by Dana Whitfield, and Paid $1,150.00.
- [ ] An end-to-end test opens the instructions page and finds the instructions with no editable field.
- [ ] Through curl on the dev backend, CLM-1002 is started, given two steps and approved at 1150.0. Then, in the browser through the Playwright MCP server, in light and dark mode:
  - the claim page shows the decision, both steps, the Coral Waiting for sign-off badge with Midnight text, and the sign-off control
  - the instructions page shows the instructions and the wording
  - both pages keep phase 4's fonts and surfaces, with no console errors
  - `uv run -m backend.seed` resets the queue afterwards
- [ ] `npm run check` passes.

## Phase 6: The pilot end to end

**Builds:** no new features. The agent works the whole queue on the real model while the dashboard is open, and the build fixes whatever problems the run shows. This phase doesn't measure accuracy, which needs the handlers' decisions in `data/evals/`, and nothing here opens them. If the model skips any of the three reads, the harness takes them over: `run` makes them in code, records them as steps and passes them to the model, following decision 4. At the end, `docs/STATUS.md` says what's built and how to run it.

**Why:** the earlier phases test the parts with stubs. This one checks they work together on real claims, the way the team will use them.

- [ ] `uv run -m agent`, running in the background, works all 25 claims and prints a line for each. On Luna at low reasoning this costs a few cents. Every claim ends `decided` or `waiting_for_sign_off`, and none is left waiting or in progress.
- [ ] Through `list_claims` and `get_claim`:
  - every claim with a decision has reasons and a policy section
  - every approval of $1,000.00 or less is paid exactly its payout
  - every approval over $1,000.00 waits for sign-off with no payment
  - every decline and referral has a payout of zero and no payment
- [ ] For every claim, `list_steps` shows "Read the claim", "Read the policy" and "Read the claim history" before "Record the decision".
- [ ] While the agent runs, the browser through the Playwright MCP server shows claims moving through the states on the queue, and the steps arriving on the page of a claim the agent hasn't reached yet.
- [ ] Signing off one claim that waits for sign-off, in the browser, shows it decided and paid, and `get_claim` agrees.
- [ ] `docs/STATUS.md` says what's built and how to run it: `npm run dev`, `uv run -m agent`, `uv run -m backend.seed` and `npm run check`.
- [ ] `npm run check` passes, and the results are reported. The run's decisions stay in the database for you to look through, and `uv run -m backend.seed` resets the queue.

## Not in this plan

- The items `docs/SPEC.md` leaves out: the claims manual, sign-in, real payments and messages to customers.
- Checking the agent against the handlers' decisions in `data/evals/`, which nothing in the product reads.
- Starting the agent from the dashboard, retrying a failed claim or rerunning a decided one. A claim left in progress, or one you want to run again, needs `uv run -m backend.seed`.
