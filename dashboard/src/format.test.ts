import { expect, it } from "vitest";
import { clock, date, label, money, STATUS_LABELS, time } from "./format";

it("formats money in US dollars", () => {
  expect(money(1250)).toBe("$1,250.00");
  expect(money(0)).toBe("$0.00");
});

it("formats dates", () => {
  expect(date("2026-06-24")).toBe("Jun 24, 2026");
  expect(time("2026-10-26T02:24:47+00:00")).toMatch(/2026/);
});

it("turns codes into labels", () => {
  expect(label("trip_delay")).toBe("Trip delay");
  expect(label("premium")).toBe("Premium");
});

it("labels each state", () => {
  expect(Object.values(STATUS_LABELS)).toEqual([
    "Waiting",
    "In progress",
    "Waiting for sign-off",
    "Decided",
  ]);
  expect(clock("2026-10-26T02:24:47+00:00")).toMatch(/:24:47/);
});
