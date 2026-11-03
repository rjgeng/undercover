import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "./App";
import type { Run } from "./api";
import { Refusal, stubApi, summary } from "./testing";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const running: Run = {
  run_id: "RUN-1a2b3c4d",
  cap: 4,
  status: "running",
  todos: [
    { content: "CLM-1001, trip delay", status: "done" },
    { content: "CLM-1002, baggage", status: "handler" },
    { content: "CLM-1003, medical", status: "in_progress" },
    { content: "CLM-1004, baggage delay", status: "todo" },
  ],
  claims: ["CLM-1001", "CLM-1002", "CLM-1003"],
  summary: null,
  started_at: "2026-11-03T10:00:00+00:00",
  finished_at: null,
};

function showQueue(run: unknown, claims = [summary]) {
  stubApi({ "GET /api/claims": claims, "GET /api/runs/latest": run });
  render(
    <MemoryRouter initialEntries={["/"]}>
      <App />
    </MemoryRouter>,
  );
}

async function runPanel() {
  return within(await screen.findByRole("region", { name: "Agent run" }));
}

it("says when there are no runs yet", async () => {
  showQueue(null);
  const panel = await runPanel();
  expect(await panel.findByText("No runs yet.")).toBeDefined();
});

it("shows a running run's to-do list, with each item's state", async () => {
  showQueue(running);
  const panel = await runPanel();
  expect(await panel.findByText("RUN-1a2b3c4d")).toBeDefined();
  expect(panel.getByText("Running")).toBeDefined();
  expect(panel.getByText(/up to 4 claims/)).toBeDefined();
  const items = within(panel.getByRole("list", { name: "To-do list" }))
    .getAllByRole("listitem")
    .map((item) => item.textContent);
  expect(items).toEqual([
    "DoneCLM-1001, trip delay",
    "Left for a handlerCLM-1002, baggage",
    "In progressCLM-1003, medical",
    "To doCLM-1004, baggage delay",
  ]);
});

it("shows a finished run with its summary", async () => {
  showQueue({
    ...running,
    cap: 1,
    status: "finished",
    todos: [],
    summary: "One claim approved and paid.",
  });
  const panel = await runPanel();
  expect(await panel.findByText("One claim approved and paid.")).toBeDefined();
  expect(panel.getByText("Finished")).toBeDefined();
  expect(panel.getByText(/up to 1 claim$/)).toBeDefined();
  expect(panel.getByText("No to-do list yet.")).toBeDefined();
});

it("shows a stopped run", async () => {
  showQueue({ ...running, status: "stopped" });
  const panel = await runPanel();
  expect(await panel.findByText("Stopped")).toBeDefined();
});

it("shows an error when the run can't load", async () => {
  showQueue(new Refusal(500, "The backend is down"));
  const panel = await runPanel();
  expect((await panel.findByRole("alert")).textContent).toBe(
    "The backend is down",
  );
});

it("counts the claims that need a handler", async () => {
  showQueue(null, [
    summary,
    { ...summary, claim_id: "CLM-1003", status: "needs_handler" },
  ]);
  expect(await screen.findByLabelText("Needs a handler: 1")).toBeDefined();
  const row = screen.getByRole("row", { name: /CLM-1003/ });
  expect(within(row).getByText("Needs a handler")).toBeDefined();
});
