import { api, type Status } from "./api";
import { date, DECISION_LABELS, label, money } from "./format";
import { StatusBadge } from "./StatusBadge";
import { useApi } from "./useApi";

const STATES: Status[] = [
  "waiting",
  "in_progress",
  "waiting_for_sign_off",
  "decided",
];

export function QueuePage() {
  const { data: claims, error } = useApi(api.claims);

  return (
    <>
      <h1>Claims queue</h1>
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
      {claims && (
        <>
          <section className="tiles" aria-label="Claims by state">
            {STATES.map((status) => (
              <div key={status} className="panel">
                <StatusBadge status={status} />
                <p className="count mono">
                  {claims.filter((claim) => claim.status === status).length}
                </p>
              </div>
            ))}
          </section>
          <section className="panel" aria-label="Claims">
            <table>
              <thead>
                <tr>
                  <th>Claim</th>
                  <th>Customer</th>
                  <th>Type</th>
                  <th>Summary</th>
                  <th className="number">Claimed</th>
                  <th>Submitted</th>
                  <th>Status</th>
                  <th>Decision</th>
                </tr>
              </thead>
              <tbody>
                {claims.map((claim) => (
                  <tr key={claim.claim_id}>
                    <td className="mono">
                      <a href={`#/claims/${claim.claim_id}`}>
                        {claim.claim_id}
                      </a>
                    </td>
                    <td>{claim.customer_name}</td>
                    <td>{label(claim.claim_type)}</td>
                    <td>{claim.summary}</td>
                    <td className="mono number">
                      {money(claim.amount_claimed)}
                    </td>
                    <td className="mono">{date(claim.submitted_on)}</td>
                    <td>
                      <StatusBadge status={claim.status} />
                    </td>
                    <td>
                      {claim.decision && DECISION_LABELS[claim.decision]}
                      {claim.decision === "approve" && (
                        <span className="mono">
                          {" "}
                          {money(claim.payout ?? 0)}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
    </>
  );
}
