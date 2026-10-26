import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { InstructionsPage } from "./InstructionsPage";
import { stubApi } from "./testing";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows the instructions and the wording, read only", async () => {
  stubApi({
    "/api/instructions": { text: "# The UnderCover Agent" },
    "/api/policy-wording": { version: "2026.1", text: "# Policy Wording" },
  });
  render(<InstructionsPage />);
  expect(await screen.findByText("# The UnderCover Agent")).toBeDefined();
  expect(
    await screen.findByText("Policy wording, version 2026.1"),
  ).toBeDefined();
  expect(screen.queryByRole("textbox")).toBeNull();
});

it("shows loading, then why a load failed", async () => {
  stubApi({});
  render(<InstructionsPage />);
  expect(screen.getAllByRole("status").map((s) => s.textContent)).toEqual([
    "Loading",
    "Loading",
  ]);
  const alerts = await screen.findAllByRole("alert");
  expect(alerts.map((a) => a.textContent)).toEqual([
    "Nothing at /api/instructions",
    "Nothing at /api/policy-wording",
  ]);
});
