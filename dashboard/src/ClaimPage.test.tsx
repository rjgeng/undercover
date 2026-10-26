import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ClaimPage } from "./ClaimPage";
import { claimRecord, claimRoutes, POLICY, step, stubApi } from "./testing";
import { EVERY } from "./useApi";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const held = claimRecord({
  status: "waiting_for_sign_off",
  decision: "approve",
  payout: 1150,
  reasons: "A covered loss.",
  policy_section: "Section 5",
  decided_at: "2026-10-26T02:24:47+00:00",
});

it("shows a waiting claim in full", async () => {
  stubApi(claimRoutes(claimRecord()));
  render(<ClaimPage claimId="CLM-1001" />);
  expect(
    await screen.findByText("My flight home from Rome was canceled."),
  ).toBeDefined();
  const claim = screen.getByRole("region", { name: "Claim" });
  expect(within(claim).getByText("Trip delay")).toBeDefined();
  expect(within(claim).getByText("$340.00")).toBeDefined();
  const items = screen.getByRole("region", { name: "Items claimed" });
  expect(within(items).getByText("$245.00")).toBeDefined();
  expect(within(items).getByText("Accommodation")).toBeDefined();
  const documents = screen.getByRole("region", { name: "Documents" });
  expect(
    within(documents).getByText("Flight MA 611 was canceled."),
  ).toBeDefined();
  expect(within(documents).getByText("Carrier report")).toBeDefined();
  expect(
    screen.getByText("The agent hasn't started on this claim."),
  ).toBeDefined();
  expect(await screen.findByText("No steps yet.")).toBeDefined();
  const policy = screen.getByRole("region", { name: "Policy" });
  expect(await within(policy).findByText("Premium")).toBeDefined();
  expect(within(policy).getByText("None")).toBeDefined();
  const customer = screen.getByRole("region", { name: "Customer" });
  expect(await within(customer).findByText(/CLM-0412/)).toBeDefined();
});

it("shows the agent at work, step by step", async () => {
  stubApi(
    claimRoutes(claimRecord({ status: "in_progress" }), [
      step(1),
      step(2, { kind: "note", title: "Note", detail: "A covered delay." }),
    ]),
  );
  render(<ClaimPage claimId="CLM-1001" />);
  expect(
    await screen.findByText("The agent is working on this claim."),
  ).toBeDefined();
  const steps = screen.getByRole("region", { name: "The agent's steps" });
  const items = await within(steps).findAllByRole("listitem");
  expect(
    items.map((item) => item.querySelector("summary")?.textContent),
  ).toEqual([
    expect.stringContaining("Read the claim"),
    expect.stringContaining("Note"),
  ]);
  expect(items[1]?.querySelector("details")?.open).toBe(true);
});

it("signs off a payout over the limit", async () => {
  const fetch = stubApi({
    ...claimRoutes(held),
    "POST /api/claims/CLM-1001/sign-off": { ...held, status: "decided" },
  });
  render(<ClaimPage claimId="CLM-1001" />);
  const decision = await screen.findByRole("region", { name: "Decision" });
  expect(within(decision).getByText("Approved")).toBeDefined();
  expect(within(decision).getByText("A covered loss.")).toBeDefined();
  expect(
    within(decision).getByText(/paid once a handler signs it off/),
  ).toBeDefined();
  const button = within(decision).getByRole("button", {
    name: "Sign off and pay $1,150.00",
  });
  expect((button as HTMLButtonElement).disabled).toBe(true);
  const options = await within(decision).findAllByRole("option");
  expect(options.map((option) => option.textContent)).toEqual([
    "Choose a handler",
    "Dana Whitfield",
  ]);
  fireEvent.change(within(decision).getByLabelText("Handler"), {
    target: { value: "HND-01" },
  });
  fireEvent.click(button);
  await waitFor(() => {
    expect(fetch).toHaveBeenCalledWith(
      "/api/claims/CLM-1001/sign-off",
      expect.objectContaining({ body: '{"handler_id":"HND-01"}' }),
    );
  });
  const claimLoads = () =>
    fetch.mock.calls.filter(([path]) => path === "/api/claims/CLM-1001").length;
  const before = claimLoads();
  await waitFor(() => {
    expect(claimLoads()).toBeGreaterThan(before);
  });
  expect(
    screen.getByRole("button", { name: /Sign off and pay/ }),
  ).toHaveProperty("disabled", true);
});

it("says why a sign-off was refused", async () => {
  stubApi(claimRoutes(held));
  render(<ClaimPage claimId="CLM-1001" />);
  fireEvent.change(await screen.findByLabelText("Handler"), {
    target: { value: "HND-01" },
  });
  fireEvent.click(screen.getByRole("button", { name: /Sign off and pay/ }));
  expect((await screen.findByRole("alert")).textContent).toBe(
    "Nothing at POST /api/claims/CLM-1001/sign-off",
  );
});

it("shows who signed off and the payment", async () => {
  stubApi(
    claimRoutes({
      ...held,
      status: "decided",
      signed_off_by: "HND-01",
      signed_off_at: "2026-10-26T03:00:00+00:00",
      paid_amount: 1150,
      paid_at: "2026-10-26T03:00:00+00:00",
    }),
  );
  render(<ClaimPage claimId="CLM-1001" />);
  const decision = await screen.findByRole("region", { name: "Decision" });
  expect(
    await within(decision).findByText(/Signed off by Dana Whitfield/),
  ).toBeDefined();
  expect(within(decision).getByText(/Paid/).textContent).toMatch(/\$1,150\.00/);
  expect(within(decision).queryByRole("button")).toBeNull();
});

it("shows an approval not yet paid, and a decline", async () => {
  stubApi(
    claimRoutes(
      claimRecord({ status: "decided", decision: "approve", payout: 340 }),
    ),
  );
  render(<ClaimPage claimId="CLM-1001" />);
  expect(await screen.findByText("Not paid yet.")).toBeDefined();
  cleanup();
  stubApi(
    claimRoutes(
      claimRecord({
        status: "decided",
        decision: "decline",
        payout: 0,
        decided_at: "2026-10-26T02:24:47+00:00",
      }),
    ),
  );
  render(<ClaimPage claimId="CLM-1001" />);
  const decision = await screen.findByRole("region", { name: "Decision" });
  expect(within(decision).getByText("Declined")).toBeDefined();
  expect(within(decision).queryByText(/\$0\.00/)).toBeNull();
  expect(within(decision).getByText(/Recorded on/)).toBeDefined();
  expect(screen.queryByText("Not paid yet.")).toBeNull();
});

it("shows each panel loading, then the error when its load fails", async () => {
  stubApi({ "/api/claims/CLM-1001": claimRecord() });
  render(<ClaimPage claimId="CLM-1001" />);
  expect(screen.getByRole("status").textContent).toBe("Loading");
  await screen.findByText("My flight home from Rome was canceled.");
  for (const [name, path] of [
    ["Policy", "/api/policies/POL-2001"],
    ["Customer", "/api/customers/CUS-3001/claims"],
    ["The agent's steps", "/api/claims/CLM-1001/steps"],
  ]) {
    const panel = screen.getByRole("region", { name });
    expect((await within(panel).findByRole("alert")).textContent).toBe(
      `Nothing at ${path}`,
    );
  }
  expect(screen.queryByText("No steps yet.")).toBeNull();
});

it("shows an error that comes after the claim has loaded", async () => {
  vi.useFakeTimers();
  stubApi(claimRoutes(claimRecord()));
  render(<ClaimPage claimId="CLM-1001" />);
  await act(() => vi.advanceTimersByTimeAsync(0));
  expect(
    screen.getByText("My flight home from Rome was canceled."),
  ).toBeDefined();
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response("", { status: 502 })),
  );
  await act(() => vi.advanceTimersByTimeAsync(EVERY));
  expect(screen.getAllByRole("alert")[0]?.textContent).toBe(
    "The backend isn't responding (502)",
  );
  expect(
    screen.getByText("My flight home from Rome was canceled."),
  ).toBeDefined();
  vi.useRealTimers();
});

it("names the add-ons as the policy wording does", async () => {
  stubApi({
    ...claimRoutes(claimRecord()),
    "/api/policies/POL-2001": {
      ...POLICY,
      add_ons: ["electronics_plus", "pre_existing_waiver"],
    },
  });
  render(<ClaimPage claimId="CLM-1001" />);
  expect(
    await screen.findByText("Electronics Plus, Pre-Existing Condition Waiver"),
  ).toBeDefined();
});

it("says when a claim doesn't exist", async () => {
  stubApi({});
  render(<ClaimPage claimId="CLM-9999" />);
  expect((await screen.findByRole("alert")).textContent).toBe(
    "Nothing at /api/claims/CLM-9999",
  );
});
