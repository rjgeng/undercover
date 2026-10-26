import { useCallback } from "react";
import { api } from "./api";
import { clock } from "./format";
import { useApi } from "./useApi";

export function Steps({ claimId }: Readonly<{ claimId: string }>) {
  const load = useCallback(() => api.steps(claimId), [claimId]);
  const { data: steps = [] } = useApi(load);
  return (
    <section className="panel" aria-label="The agent's steps">
      <h2>The agent&apos;s steps</h2>
      {steps.length === 0 ? (
        <p className="muted">No steps yet.</p>
      ) : (
        <ol className="steps">
          {steps.map((step) => (
            <li key={step.step_id}>
              <details open={step.kind === "note"}>
                <summary>
                  <span className="mono muted">{clock(step.created_at)}</span>{" "}
                  {step.title}
                </summary>
                <pre className={step.kind === "note" ? "text" : undefined}>
                  {step.detail}
                </pre>
              </details>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
