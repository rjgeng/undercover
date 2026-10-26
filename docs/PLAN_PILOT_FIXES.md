# Plan: fixes to the pilot from the comparison with Ed's build

The comparison of `week1day3-rj` with Ed's `week1day3-end`, checked claim by claim by a second agent, found places where Ed's build does better. This plan takes the ones `docs/SPEC.md`, `docs/TECH_STACK.md` and `docs/PROCESS.md` ask for. It builds on the pilot in `docs/PLAN.md` and keeps its decisions, except where a phase below changes one.

There are four phases. Each one ends with every check green, its criteria ticked, `docs/STATUS.md` updated and a commit.

## Left out, and why

- **The queue run carrying on after a failed claim.** Ed's build does this, but it belongs to the Week 1 Day 5 brief ("One bad claim must never stop the run").
- **Ed's prompt lines taken from the claims manual.** Two of them closely paraphrase `data/claims_manual.md`, which the spec keeps out of the pilot. Phase 4 takes the shape of Ed's prompt, a procedure, but takes its rules only from the policy wording and the spec.
- **React Router, a typed error class and a total row for the items.** The comparison found these differences matter little.

## Phase 1: The backend refuses bad input and serves no personal data

**Builds:**

- **Text that must not be empty:** a decision's `reasons` and `policy_section`, a start's `thread_id`, and a step's `title` and `detail` must have at least one character that isn't a space (422 otherwise). A decision is final, so a decision with no explanation could never be put right.
- **No steps on a claim nobody has started:** `add_step` answers 409 for a waiting claim. Steps on a claim waiting for sign-off or decided are still allowed, because the harness records the payment and the final reply after the decision.
- **The claim history on its own:** a new operation `get_claim_history`, `GET /api/customers/{customer_id}/claims`, returns only the customer's earlier claims. It replaces `get_customer`, so no route serves anyone's email, phone, date of birth or address. `get_claim` gains `customer_name` for the dashboard, as `list_claims` already has. The claim page loses the "Customer since" line, which nothing in the spec asks for.
- **UTF-8:** every file the backend reads is read as UTF-8, so a character outside ASCII in `data/` or the instructions reads the same on Windows.
- **Built in this phase as well:** the agent's history tool and the dashboard's customer panel move to the new operation here, not in phases 2 and 3, because removing `get_customer` would otherwise break them. The handlers' list drops the handlers' emails too, which nothing shows, so no route serves anyone's email.

**Why:** the spec asks for each decision's explanation and section, and `data/README.md` calls the customer records personal data. Both rules belong in the backend, where they hold whoever calls.

- [x] Tests: approving with empty or blank reasons or section gets 422 and the claim stays in progress; a start with an empty thread id gets 422; a step with an empty title or detail gets 422; a step on a waiting claim gets 409; a step on a decided claim succeeds.
- [x] A test calls every GET operation for CLM-1001 and its policy and customer, and none of the responses contains Maya Patel's email, phone, date of birth or street.
- [x] `curl -s localhost:8000/api/customers/CUS-3001/claims` returns one earlier claim, CLM-0412, and `curl -s -w '\n%{http_code}\n' localhost:8000/api/customers/CUS-3001` gives 404.
- [x] `curl -s localhost:8000/api/claims/CLM-1001` includes `"customer_name":"Maya Patel"`.
- [x] The test that every operation sets its own `operation_id` passes with `get_claim_history` in place of `get_customer`.
- [x] `npm run check` passes.

## Phase 2: The agent uses the new operation and reads refusals plainly

**Builds:**

- `get_claim_history` calls the new operation, and passes its answer straight through.
- When a refusal's detail is FastAPI's list of validation errors, the tool turns it into plain text, such as `Refused: payout: Input should be greater than or equal to 0`, rather than a Python list.
- The command line flushes each line as it prints, so a run in the background shows each claim as it finishes.

**Why:** the agent should read the same refusals a person would, and a long run should show its progress.

- [x] A stub-model test records a decision with empty reasons, gets the plain refusal back, records it again with reasons and ends `decided`.
- [x] A stub-model test of a negative payout gets `Refused: payout: Input should be greater than or equal to 0`.
- [x] The existing agent tests pass with the new history operation, and the history step still shows CLM-0412 and no email.
- [x] `npm run check` passes.

## Phase 3: The dashboard shows loading, errors and decisions clearly

**Builds:**

- **Loading and errors in every panel:** one small component shows "Loading" with `role="status"` or the error with `role="alert"`. It's used in the policy, customer history and steps panels and on the instructions page, so a failed load never reads as "No steps yet." The claim page also shows an error that comes after the claim has loaded, as the queue does.
- **The decision:** a decline or referral shows no payout, and the panel shows when the decision was made.
- **Sign-off:** the button stays disabled after a successful sign-off, so a second click can't send a second request.
- **Names:** add-ons show their names from the policy wording (Adventure Sports, Pre-Existing Condition Waiver, Electronics Plus), and the customer panel takes the name from the claim and the earlier claims from the new operation.
- **The alert:** it stays Raspberry with white text, as `docs/BRAND.md` says, but in large bold text, which is what WCAG AA asks of white on Raspberry (3.6 to 1 passes for large text).
- **Navigation:** the header link for the current page has `aria-current="page"`.

**Why:** a handler must be able to tell "failed" from "empty", and these are small changes that the comparison found Ed's build makes.

- [x] Vitest tests: each panel shows "Loading" and then its data; each panel shows the error when its load fails, and the steps panel then doesn't say "No steps yet."; the claim page shows an error after a later poll fails; a decline shows "Declined" and no "$0.00"; the decided time shows; the sign-off button stays disabled after success; add-on names; `aria-current` on the current page.
- [x] The end-to-end tests pass, with the claim test finding CLM-0412 in the customer panel.
- [x] In the browser (Playwright scripts with Chromium, since the Playwright MCP server needs Chrome), in light and dark mode: the claim page of a declined claim, set up through curl, shows no "$0.00" and shows the decided time. With the backend down (a second dashboard on port 5175 whose proxy points at a closed port, so `npm run dev` keeps running), the queue, the claim page and the instructions page each show "The backend isn't responding (502)". The alert's text is at least 18.66px and bold.
- [x] `npm run check` passes.

## Phase 4: A procedural prompt drawn from the wording, and a second queue run

**Builds:** `backend/instructions.md` becomes a short numbered procedure, with every rule taken from the policy wording or the spec, and none from the claims manual:

1. Read the claim with `get_claim`. It gives the policy id and the customer id, so never guess them.
2. Read the policy and the claim history with those ids.
3. Check that the incident falls within the covered trip (sections 9 and 12) and that the claim was filed within 90 days of it (section 11).
4. Find the benefit the claim falls under, and check its conditions and exclusions, the general exclusions (section 9) and any add-on on the policy (section 8).
5. Decide. The goal is to handle claims straight through (the spec), so refer only when a document the wording asks for is missing (section 11) or the wording doesn't settle the claim.
6. For an approval, work out the payout step by step as section 10 sets out: each item up to the per-item limit, less what a carrier or anyone else paid, less the deductible where section 1 applies it, up to the benefit's maximum.
7. Record the decision with two or three sentences and the section. Then pay an approval, except one over $1,000, which waits for a handler.

**Why:** the first run's model guessed ids before reading the claim, and the comparison suggests a procedure helps a small model at low effort. The decisions may change, so this phase runs the whole queue again.

- [ ] A test checks the instructions name the five tools, mention sections 9, 10 and 11, and don't mention the manual.
- [ ] The stub-model tests still pass.
- [ ] `uv run -m backend.seed`, then `uv run -m agent` works all 25 claims on GPT-6 Luna at low reasoning, a few cents again. Every claim ends `decided` or `waiting_for_sign_off`, and every approval of $1,000.00 or less is paid.
- [ ] Every claim's first step is "Read the claim", and no step is a refusal for a guessed id.
- [ ] The run's time and its decisions (approve, decline, refer and held) go in `docs/STATUS.md` next to the first run's. They can't be scored, because that needs `data/evals/`.
- [ ] `npm run check` passes, and the results are reported.
