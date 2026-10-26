import type { Decision, Status } from "./api";

const dollars = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});
const day = new Intl.DateTimeFormat("en-US", {
  dateStyle: "medium",
  timeZone: "UTC",
});
const moment = new Intl.DateTimeFormat("en-US", {
  dateStyle: "medium",
  timeStyle: "short",
});
const seconds = new Intl.DateTimeFormat("en-US", { timeStyle: "medium" });

export const STATUS_LABELS: Record<Status, string> = {
  waiting: "Waiting",
  in_progress: "In progress",
  waiting_for_sign_off: "Waiting for sign-off",
  decided: "Decided",
};

export const DECISION_LABELS: Record<Decision, string> = {
  approve: "Approved",
  decline: "Declined",
  refer: "Referred",
};

export function money(amount: number): string {
  return dollars.format(amount);
}

export function date(iso: string): string {
  return day.format(new Date(iso));
}

export function time(iso: string): string {
  return moment.format(new Date(iso));
}

export function clock(iso: string): string {
  return seconds.format(new Date(iso));
}

export function label(code: string): string {
  const words = code.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
