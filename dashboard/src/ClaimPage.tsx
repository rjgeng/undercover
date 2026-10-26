import { useCallback } from "react";
import { api, type Claim, type Handler } from "./api";
import { date, DECISION_LABELS, label, money, time } from "./format";
import { SignOff } from "./SignOff";
import { StatusBadge } from "./StatusBadge";
import { Steps } from "./Steps";
import { useApi } from "./useApi";

export function ClaimPage({ claimId }: Readonly<{ claimId: string }>) {
  const loadClaim = useCallback(() => api.claim(claimId), [claimId]);
  const { data: claim, error, reload } = useApi(loadClaim);
  const { data: handlers = [] } = useApi(api.handlers, false);

  if (!claim) {
    return error ? (
      <p className="alert" role="alert">
        {error}
      </p>
    ) : (
      <p className="muted">Loading the claim</p>
    );
  }
  return (
    <>
      <p>
        <a href="#/">Back to the queue</a>
      </p>
      <div className="title">
        <h1>
          <span className="mono">{claim.claim_id}</span> {claim.summary}
        </h1>
        <StatusBadge status={claim.status} />
      </div>
      <div className="columns">
        <div>
          <ClaimDetails claim={claim} />
          <Steps claimId={claimId} />
        </div>
        <div>
          <DecisionPanel claim={claim} handlers={handlers} onChange={reload} />
          <PolicyPanel policyId={claim.policy_id} />
          <CustomerPanel claim={claim} />
        </div>
      </div>
    </>
  );
}

function ClaimDetails({ claim }: Readonly<{ claim: Claim }>) {
  return (
    <>
      <section className="panel" aria-label="Claim">
        <h2>The claim</h2>
        <dl className="facts">
          <dt>Type</dt>
          <dd>{label(claim.claim_type)}</dd>
          <dt>Submitted</dt>
          <dd className="mono">{date(claim.submitted_on)}</dd>
          <dt>Incident</dt>
          <dd>
            <span className="mono">{date(claim.incident_date)}</span>,{" "}
            {claim.incident_location}
          </dd>
          <dt>Amount claimed</dt>
          <dd className="mono">{money(claim.amount_claimed)}</dd>
        </dl>
        <h3>The customer&apos;s story</h3>
        <p>{claim.story}</p>
      </section>
      <section className="panel" aria-label="Items claimed">
        <h2>Items claimed</h2>
        <table>
          <thead>
            <tr>
              <th>Item</th>
              <th>Category</th>
              <th className="number">Amount</th>
            </tr>
          </thead>
          <tbody>
            {claim.items.map((item) => (
              <tr key={item.description}>
                <td>{item.description}</td>
                <td>{label(item.category)}</td>
                <td className="mono number">{money(item.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="panel" aria-label="Documents">
        <h2>Documents</h2>
        {claim.documents.map((document) => (
          <article key={document.name} className="document">
            <h3>{document.name}</h3>
            <p className="muted">{label(document.type)}</p>
            <p>{document.content}</p>
          </article>
        ))}
      </section>
    </>
  );
}

function DecisionPanel({
  claim,
  handlers,
  onChange,
}: Readonly<{ claim: Claim; handlers: Handler[]; onChange: () => void }>) {
  const signer = handlers.find((h) => h.handler_id === claim.signed_off_by);
  return (
    <section className="panel" aria-label="Decision">
      <h2>Decision</h2>
      {claim.decision === null ? (
        <p className="muted">
          {claim.status === "waiting"
            ? "The agent hasn't started on this claim."
            : "The agent is working on this claim."}
        </p>
      ) : (
        <>
          <p className="decision">
            {DECISION_LABELS[claim.decision]}{" "}
            <span className="mono">{money(claim.payout ?? 0)}</span>
          </p>
          <p>{claim.reasons}</p>
          <p className="muted">Policy section: {claim.policy_section}</p>
          {claim.signed_off_at && (
            <p>
              Signed off by {signer?.name ?? claim.signed_off_by} on{" "}
              <span className="mono">{time(claim.signed_off_at)}</span>
            </p>
          )}
          <Payment claim={claim} />
          {claim.status === "waiting_for_sign_off" && (
            <SignOff claim={claim} handlers={handlers} onDone={onChange} />
          )}
        </>
      )}
    </section>
  );
}

function Payment({ claim }: Readonly<{ claim: Claim }>) {
  if (claim.paid_amount !== null && claim.paid_at !== null) {
    return (
      <p>
        Paid <span className="mono">{money(claim.paid_amount)}</span> on{" "}
        <span className="mono">{time(claim.paid_at)}</span>
      </p>
    );
  }
  if (claim.status === "waiting_for_sign_off") {
    return <p>This payout is paid once a handler signs it off.</p>;
  }
  return claim.decision === "approve" ? <p>Not paid yet.</p> : null;
}

function PolicyPanel({ policyId }: Readonly<{ policyId: string }>) {
  const load = useCallback(() => api.policy(policyId), [policyId]);
  const { data: policy } = useApi(load, false);
  return (
    <section className="panel" aria-label="Policy">
      <h2>
        Policy <span className="mono">{policyId}</span>
      </h2>
      {policy && (
        <dl className="facts">
          <dt>Plan</dt>
          <dd>{label(policy.plan)}</dd>
          <dt>Add-ons</dt>
          <dd>{policy.add_ons.map(label).join(", ") || "None"}</dd>
          <dt>Bought</dt>
          <dd>
            <span className="mono">{date(policy.purchased_on)}</span>, through{" "}
            {policy.sold_through}
          </dd>
          <dt>Trip</dt>
          <dd>
            {policy.trip.destination},{" "}
            <span className="mono">
              {date(policy.trip.departs_on)} to {date(policy.trip.returns_on)}
            </span>
          </dd>
          <dt>Trip cost</dt>
          <dd className="mono">{money(policy.trip.trip_cost)}</dd>
          <dt>Travelers</dt>
          <dd>{policy.travelers.join(", ")}</dd>
        </dl>
      )}
    </section>
  );
}

function CustomerPanel({ claim }: Readonly<{ claim: Claim }>) {
  const load = useCallback(
    () => api.history(claim.customer_id),
    [claim.customer_id],
  );
  const { data: history } = useApi(load, false);
  return (
    <section className="panel" aria-label="Customer">
      <h2>{claim.customer_name}</h2>
      <h3>Earlier claims</h3>
      {history?.length === 0 && <p className="muted">None.</p>}
      {history && history.length > 0 && (
        <ul className="history">
          {history.map((earlier) => (
            <li key={earlier.claim_id}>
              <span className="mono">{earlier.claim_id}</span>,{" "}
              <span className="mono">{date(earlier.filed_on)}</span>:{" "}
              {earlier.summary}. {label(earlier.outcome)},{" "}
              <span className="mono">{money(earlier.amount_paid)}</span> paid.
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
