import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ClaimSummary } from "./api";
import { QueuePage } from "./QueuePage";
import { stubApi, summary } from "./testing";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function some(count: number, first: number, changes: Partial<ClaimSummary>) {
  return Array.from({ length: count }, (_, n) =>
    summary(`CLM-${String(first + n)}`, changes),
  );
}

it("counts the claims in each state and lists them", async () => {
  stubApi({
    "/api/claims": [
      ...some(3, 1001, {}),
      ...some(2, 1004, { status: "in_progress" }),
      ...some(1, 1006, {
        status: "waiting_for_sign_off",
        decision: "approve",
        payout: 1150,
      }),
      ...some(4, 1007, { status: "decided", decision: "refer", payout: 0 }),
    ],
  });
  render(<QueuePage />);
  expect(screen.getByRole("status").textContent).toBe("Loading");
  const row = await screen.findByRole("row", { name: /CLM-1006/ });
  expect(within(row).getByText("Waiting for sign-off")).toBeDefined();
  expect(within(row).getByText("Approved")).toBeDefined();
  expect(within(row).getByText("$1,150.00")).toBeDefined();
  expect(within(row).getByText("$420.00")).toBeDefined();
  expect(within(row).getByText("Jun 24, 2026")).toBeDefined();
  expect(within(row).getByText("Trip delay")).toBeDefined();
  expect(
    within(row).getByRole("link", { name: "CLM-1006" }).getAttribute("href"),
  ).toBe("#/claims/CLM-1006");
  const referred = screen.getByRole("row", { name: /CLM-1010/ });
  expect(within(referred).getByText("Referred")).toBeDefined();
  const tiles = screen.getByRole("region", { name: "Claims by state" });
  expect(
    Array.from(tiles.querySelectorAll(".panel")).map((tile) => [
      tile.querySelector(".badge")?.textContent,
      tile.querySelector(".count")?.textContent,
    ]),
  ).toEqual([
    ["Waiting", "3"],
    ["In progress", "2"],
    ["Waiting for sign-off", "1"],
    ["Decided", "4"],
  ]);
  expect(screen.getAllByRole("row")).toHaveLength(11);
});

it("says when the backend isn't responding", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response("", { status: 502 })),
  );
  render(<QueuePage />);
  expect((await screen.findByRole("alert")).textContent).toBe(
    "The backend isn't responding (502)",
  );
});
