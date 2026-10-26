export type Status =
  "waiting" | "in_progress" | "waiting_for_sign_off" | "decided";
export type Decision = "approve" | "decline" | "refer";

export interface ClaimSummary {
  claim_id: string;
  customer_name: string;
  claim_type: string;
  summary: string;
  amount_claimed: number;
  submitted_on: string;
  status: Status;
  decision: Decision | null;
  payout: number | null;
}

export interface Item {
  description: string;
  category: string;
  amount: number;
}

export interface ClaimDocument {
  name: string;
  type: string;
  content: string;
}

export interface Claim {
  claim_id: string;
  policy_id: string;
  customer_id: string;
  claim_type: string;
  submitted_on: string;
  incident_date: string;
  incident_location: string;
  summary: string;
  story: string;
  items: Item[];
  amount_claimed: number;
  documents: ClaimDocument[];
  status: Status;
  thread_id: string | null;
  decision: Decision | null;
  payout: number | null;
  reasons: string | null;
  policy_section: string | null;
  decided_at: string | null;
  signed_off_by: string | null;
  signed_off_at: string | null;
  paid_amount: number | null;
  paid_at: string | null;
}

export interface Policy {
  policy_id: string;
  customer_id: string;
  plan: string;
  add_ons: string[];
  purchased_on: string;
  sold_through: string;
  trip: {
    destination: string;
    departs_on: string;
    returns_on: string;
    trip_cost: number;
  };
  travelers: string[];
  status: string;
}

export interface PreviousClaim {
  claim_id: string;
  filed_on: string;
  incident_date: string;
  claim_type: string;
  summary: string;
  outcome: string;
  amount_paid: number;
}

export interface Customer {
  customer_id: string;
  name: string;
  email: string;
  phone: string;
  customer_since: string;
  previous_claims: PreviousClaim[];
}

export interface Handler {
  handler_id: string;
  name: string;
  role: string;
  can_approve_over_limit: boolean;
}

export interface Step {
  step_id: number;
  kind: "tool" | "note";
  title: string;
  detail: string;
  created_at: string;
}

export interface PolicyWording {
  version: string;
  text: string;
}

async function read(response: Response): Promise<unknown> {
  const body: unknown = await response.json();
  if (!response.ok) throw new Error((body as { detail: string }).detail);
  return body;
}

function get(path: string): Promise<unknown> {
  return fetch(path).then(read);
}

function post(path: string, body: object): Promise<unknown> {
  return fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(read);
}

export const api = {
  claims: () => get("/api/claims") as Promise<ClaimSummary[]>,
  claim: (id: string) => get(`/api/claims/${id}`) as Promise<Claim>,
  steps: (id: string) => get(`/api/claims/${id}/steps`) as Promise<Step[]>,
  policy: (id: string) => get(`/api/policies/${id}`) as Promise<Policy>,
  customer: (id: string) => get(`/api/customers/${id}`) as Promise<Customer>,
  handlers: () => get("/api/handlers") as Promise<Handler[]>,
  wording: () => get("/api/policy-wording") as Promise<PolicyWording>,
  instructions: () => get("/api/instructions") as Promise<{ text: string }>,
  signOff: (id: string, handlerId: string) =>
    post(`/api/claims/${id}/sign-off`, {
      handler_id: handlerId,
    }) as Promise<Claim>,
};
