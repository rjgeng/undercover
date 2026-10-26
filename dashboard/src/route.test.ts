import { act, renderHook } from "@testing-library/react";
import { expect, it } from "vitest";
import { parseRoute, useRoute } from "./route";

it("parses the hash routes", () => {
  expect(parseRoute("")).toEqual({ page: "queue" });
  expect(parseRoute("#/")).toEqual({ page: "queue" });
  expect(parseRoute("#/claims/CLM-1001")).toEqual({
    page: "claim",
    claimId: "CLM-1001",
  });
  expect(parseRoute("#/claims/")).toEqual({ page: "queue" });
  expect(parseRoute("#/instructions")).toEqual({ page: "instructions" });
  expect(parseRoute("#/somewhere")).toEqual({ page: "queue" });
});

it("follows the hash as it changes", () => {
  const { result, unmount } = renderHook(useRoute);
  expect(result.current).toEqual({ page: "queue" });
  act(() => {
    window.location.hash = "#/instructions";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
  expect(result.current).toEqual({ page: "instructions" });
  unmount();
  window.location.hash = "";
});
