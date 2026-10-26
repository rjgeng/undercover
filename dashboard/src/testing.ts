import { vi } from "vitest";
import type { ClaimSummary } from "./api";

export function stubApi(routes: Record<string, unknown>) {
  const fetch = vi.fn((path: string, init?: RequestInit) => {
    const key = init?.method === "POST" ? `POST ${path}` : path;
    const body = routes[key];
    const response =
      body === undefined
        ? new Response(JSON.stringify({ detail: `Nothing at ${key}` }), {
            status: 404,
          })
        : new Response(JSON.stringify(body));
    return Promise.resolve(response);
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

export function summary(
  claimId: string,
  changes: Partial<ClaimSummary> = {},
): ClaimSummary {
  return {
    claim_id: claimId,
    customer_name: "Maya Patel",
    claim_type: "trip_delay",
    summary: "Flight home canceled by the airline",
    amount_claimed: 420,
    submitted_on: "2026-06-24",
    status: "waiting",
    decision: null,
    payout: null,
    ...changes,
  };
}
