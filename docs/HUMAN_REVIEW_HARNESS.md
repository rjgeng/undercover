# Human review: the harness

A human read the code after the build, even though `npm run check` is green and two live cap-5 runs
decided 5/5 correctly (the $1,000 sign-off held each time). The review checked the code against the
standards we expect when moving from a pilot to production, not just whether the tests pass.

**The good news first:** this build is clean against the usual failure modes. The backend URL lives in one
place and is read from `UNDERCOVER_API`; `request`/`reply`/`call_backend` are each defined once with no
duplication; the imports form a clean one-way chain (`tools` ← `main` ← `queue` ← `__main__`) with no cycles;
`run_queue` is short; harness and domain code are in separate modules; and every money and state guarantee is
enforced in the backend, not trusted to the agent. Do not "fix" these — confirm they are as described, and
keep them.

The review found one design issue and two minor ones. For each: **confirm** it, **decide or fix** it (some are
decisions, not automatic changes), **investigate** whether the same thing appears elsewhere, **retest** with
`npm run check`, and finally **update the process docs** so the standard is captured.

## 1. The agent instructions are scripted workflows, not goal + tools

`backend/instructions/queue.md` and `backend/instructions/claim.md` are written as numbered step-by-step
procedures. `queue.md` in particular walks the agent through a near-deterministic loop (list the claims, plan
the to-do list, for each claim mark it in progress, call `work_claim`, update the item, check for missed
claims, finish) — the model's only real judgment is the order of claims and the summary. This is the
"autonomy you don't need" red flag: a fixed workflow that could largely be code.

- Confirm this reading of both instruction files.
- Decide, and write the decision down: either (a) move the queue agent toward **goal + tools** (state the
  goal and the rules, let it choose how, keep only the judgment the model actually adds), or (b) keep the
  queue orchestration as deterministic code and reserve the model for where judgment is real. Do not silently
  leave it scripted — make the choice explicit.
- For `claim.md`: the always-read sections in steps 1–4 are fixed; consider whether those belong in the agent's
  context up front rather than as scripted tool calls. **Keep step 5 (the claim-specific look-ups) agentic** —
  that is the behaviour "What the agent read" is meant to show.

## 2. Approve-for-$0 is enforced only by the instructions

`claim.md` tells the agent "an approval always has a payout above $0", but the backend's `record_decision`
does not refuse an `approve` with a `payout` of 0. A rule the business cares about should be enforced where it
can't be bypassed.

- Decide whether an approve-for-$0 should be a backend error (like the other guarantees) or stay a prompt
  rule, and say why. If it should be enforced, add it with a test.

## 3. A new HTTP client is opened for every backend call

`request()` in `agent/tools.py` opens a new `httpx.Client` per call. It is correct and simple, but wasteful
over a run of many claims.

- Decide whether to reuse a client; low priority. Note the decision either way.

## Then, for all three

- Investigate whether the same patterns appear anywhere else in `agent/`, `backend/` and `dashboard/src`.
- Retest: `npm run check` stays green.
- Update the process docs so this doesn't recur, and report what changed:
  - `docs/PROCESS.md` — add the human-code-review step after a build, and the pilot→production standards bar.
  - `docs/CODE_STANDARDS.md` — record the standards this review relied on: prefer goal + tools over scripted
    instructions; enforce money/state rules in the backend, not the prompt; one place for backend I/O and
    config; keep harness and domain code separated.
  - `docs/STATUS.md` — note the review was done, the decisions made, and anything deferred.
