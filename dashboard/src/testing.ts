import { vi } from "vitest";
import type {
  Claim,
  ClaimSummary,
  Customer,
  Handler,
  Policy,
  Step,
} from "./api";

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

export function claimRecord(changes: Partial<Claim> = {}): Claim {
  return {
    claim_id: "CLM-1001",
    policy_id: "POL-2001",
    customer_id: "CUS-3001",
    claim_type: "trip_delay",
    submitted_on: "2026-06-24",
    incident_date: "2026-06-18",
    incident_location: "Rome, Italy",
    summary: "Flight home canceled by the airline",
    story: "My flight home from Rome was canceled.",
    items: [
      { description: "Airport hotel", category: "accommodation", amount: 245 },
      { description: "Dinner and breakfast", category: "meals", amount: 95 },
    ],
    amount_claimed: 340,
    documents: [
      {
        name: "Cancellation notice",
        type: "carrier_report",
        content: "Flight MA 611 was canceled.",
      },
    ],
    status: "waiting",
    thread_id: null,
    decision: null,
    payout: null,
    reasons: null,
    policy_section: null,
    decided_at: null,
    signed_off_by: null,
    signed_off_at: null,
    paid_amount: null,
    paid_at: null,
    ...changes,
  };
}

export const POLICY: Policy = {
  policy_id: "POL-2001",
  customer_id: "CUS-3001",
  plan: "premium",
  add_ons: [],
  purchased_on: "2026-04-22",
  sold_through: "Meridian Air checkout",
  trip: {
    destination: "Rome, Italy",
    departs_on: "2026-06-10",
    returns_on: "2026-06-18",
    trip_cost: 3100,
  },
  travelers: ["Maya Patel"],
  status: "active",
};

export const CUSTOMER: Customer = {
  customer_id: "CUS-3001",
  name: "Maya Patel",
  email: "maya.patel@example.com",
  phone: "+1 201 555 0143",
  customer_since: "2023-04-11",
  previous_claims: [
    {
      claim_id: "CLM-0412",
      filed_on: "2024-08-19",
      incident_date: "2024-08-09",
      claim_type: "baggage_delay",
      summary: "Checked bag arrived 30 hours late in Lisbon",
      outcome: "approved",
      amount_paid: 140,
    },
  ],
};

export const HANDLERS: Handler[] = [
  {
    handler_id: "HND-01",
    name: "Dana Whitfield",
    role: "Senior Claims Handler",
    can_approve_over_limit: true,
  },
  {
    handler_id: "HND-09",
    name: "Sam Trainee",
    role: "Trainee",
    can_approve_over_limit: false,
  },
];

export function step(stepId: number, changes: Partial<Step> = {}): Step {
  return {
    step_id: stepId,
    kind: "tool",
    title: "Read the claim",
    detail: '{"claim_id": "CLM-1001"}',
    created_at: "2026-10-26T02:24:47+00:00",
    ...changes,
  };
}

export function claimRoutes(claim: Claim, steps: Step[] = []) {
  return {
    "/api/claims/CLM-1001": claim,
    "/api/claims/CLM-1001/steps": steps,
    "/api/policies/POL-2001": POLICY,
    "/api/customers/CUS-3001": CUSTOMER,
    "/api/handlers": HANDLERS,
  };
}
