import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { EVERY, usePolling } from "./usePolling";

afterEach(() => {
  vi.useRealTimers();
});

it("loads now, then again every two seconds", async () => {
  vi.useFakeTimers();
  const load = vi
    .fn<() => Promise<number>>()
    .mockResolvedValueOnce(1)
    .mockResolvedValue(2);
  const { result, unmount } = renderHook(() => usePolling(load));
  await act(() => vi.advanceTimersByTimeAsync(0));
  expect(result.current.data).toBe(1);
  await act(() => vi.advanceTimersByTimeAsync(EVERY));
  expect(result.current.data).toBe(2);
  unmount();
  await vi.advanceTimersByTimeAsync(EVERY * 2);
  expect(load).toHaveBeenCalledTimes(2);
});

it("reloads on request and reports errors", async () => {
  const load = vi
    .fn<() => Promise<number>>()
    .mockRejectedValueOnce(new Error("Backend is down"))
    .mockRejectedValueOnce("odd")
    .mockResolvedValue(3);
  const { result } = renderHook(() => usePolling(load));
  await vi.waitFor(() => {
    expect(result.current.error).toBe("Backend is down");
  });
  act(() => {
    result.current.reload();
  });
  await vi.waitFor(() => {
    expect(result.current.error).toBe("Failed");
  });
  act(() => {
    result.current.reload();
  });
  await vi.waitFor(() => {
    expect(result.current.data).toBe(3);
  });
  expect(result.current.error).toBeUndefined();
});
