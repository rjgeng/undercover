import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { stubApi, summary } from "./testing";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows the header and the queue", async () => {
  stubApi({ "/api/claims": [summary("CLM-1001")] });
  render(<App />);
  expect(screen.getByRole("link", { name: "Instructions" })).toBeDefined();
  expect(await screen.findByRole("link", { name: "CLM-1001" })).toBeDefined();
});
