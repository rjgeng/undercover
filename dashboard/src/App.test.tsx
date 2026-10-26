import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { claimRecord, claimRoutes, stubApi, summary } from "./testing";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.location.hash = "";
});

function go(hash: string) {
  act(() => {
    window.location.hash = hash;
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
}

it("moves between the queue, a claim and the instructions", async () => {
  stubApi({
    ...claimRoutes(claimRecord()),
    "/api/claims": [summary("CLM-1001")],
    "/api/instructions": { text: "The instructions" },
    "/api/policy-wording": { version: "2026.1", text: "The wording" },
  });
  render(<App />);
  expect(
    await screen.findByRole("heading", { name: "Claims queue" }),
  ).toBeDefined();
  const queue = screen.getByRole("link", { name: "Queue" });
  const instructions = screen.getByRole("link", { name: "Instructions" });
  expect(queue.getAttribute("aria-current")).toBe("page");
  expect(instructions.getAttribute("aria-current")).toBeNull();
  go("#/claims/CLM-1001");
  expect(await screen.findByText("Back to the queue")).toBeDefined();
  go("#/instructions");
  expect(await screen.findByText("The instructions")).toBeDefined();
  expect(instructions.getAttribute("aria-current")).toBe("page");
  expect(queue.getAttribute("aria-current")).toBeNull();
});
