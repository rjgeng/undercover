import { expect, it } from "vitest";
import { date, decisionText, label, money, time } from "./format";

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

it("describes a decision", () => {
  expect(decisionText(null, null)).toBe("");
  expect(decisionText("approve", 1150)).toBe("Approved, $1,150.00");
  expect(decisionText("decline", 0)).toBe("Declined");
  expect(decisionText("refer", 0)).toBe("Referred");
});
