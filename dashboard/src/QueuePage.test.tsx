import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { QueuePage } from "./QueuePage";
import { stubApi, summary } from "./testing";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("counts the claims in each state and lists them", async () => {
  stubApi({
    "/api/claims": [
      summary("CLM-1001"),
      summary("CLM-1002", { status: "in_progress" }),
      summary("CLM-1003", {
        status: "waiting_for_sign_off",
        decision: "approve",
        payout: 1150,
      }),
      summary("CLM-1004", { status: "decided", decision: "refer", payout: 0 }),
    ],
  });
  render(<QueuePage />);
  const row = await screen.findByRole("row", { name: /CLM-1003/ });
  expect(within(row).getByText("Waiting for sign-off")).toBeDefined();
  expect(within(row).getByText("Approved, $1,150.00")).toBeDefined();
  expect(within(row).getByText("$420.00")).toBeDefined();
  expect(within(row).getByText("Jun 24, 2026")).toBeDefined();
  expect(within(row).getByText("Trip delay")).toBeDefined();
  expect(
    within(row).getByRole("link", { name: "CLM-1003" }).getAttribute("href"),
  ).toBe("#/claims/CLM-1003");
  const tiles = screen.getByRole("region", { name: "Claims by state" });
  expect(
    Array.from(tiles.querySelectorAll(".count")).map((c) => c.textContent),
  ).toEqual(["1", "1", "1", "1"]);
  expect(screen.getAllByRole("row")).toHaveLength(5);
});

it("says when the backend can't be reached", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("Offline")));
  render(<QueuePage />);
  expect((await screen.findByRole("alert")).textContent).toBe("Offline");
});
