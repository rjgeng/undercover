import { useCallback } from "react";
import { Link } from "react-router";
import { api, type Step } from "../api";
import { time } from "../format";
import { REFRESH_MS, useLoad } from "../useLoad";
import { Message } from "./Message";

const SUMMARY_LENGTH = 90;

export function StepList({ claimId }: Readonly<{ claimId: string }>) {
  const load = useCallback(() => api.listSteps(claimId), [claimId]);
  const { data: steps, error } = useLoad(load, REFRESH_MS);
  const reads = steps?.filter((step) => step.kind === "read") ?? [];

  return (
    <>
      <section className="panel" aria-labelledby="reads-title">
        <h2 id="reads-title">What the agent read</h2>
        <p className="small muted">
          Beyond the sections every claim starts with, in its{" "}
          <Link to="/instructions">instructions</Link>, these are the ones it
          looked up for this claim.
        </p>
        {reads.length === 0 ? (
          <p className="muted">No sections read yet.</p>
        ) : (
          <ul className="reads">
            {reads.map((step) => (
              <li key={step.step_id}>{step.content}</li>
            ))}
          </ul>
        )}
      </section>
      <section className="panel" aria-labelledby="steps-title">
        <h2 id="steps-title">Agent at work</h2>
        {!steps && <Message error={error} />}
        {steps?.length === 0 && (
          <p className="muted">
            No steps yet. They appear here as the agent works.
          </p>
        )}
        {steps && steps.length > 0 && (
          <ol className="steps">
            {steps.map((step) => (
              <li key={step.step_id} className={`step step-${step.kind}`}>
                <span className="step-time small muted">
                  {time(step.created_at)}
                </span>
                <StepBody step={step} />
              </li>
            ))}
          </ol>
        )}
      </section>
    </>
  );
}

function StepBody({ step }: Readonly<{ step: Step }>) {
  if (step.kind === "tool_call")
    return (
      <p>
        <span className="step-label">Called</span>{" "}
        <code className="mono">{step.content}</code>
      </p>
    );
  if (step.kind === "tool_result") {
    const summary =
      step.content.length > SUMMARY_LENGTH
        ? `${step.content.slice(0, SUMMARY_LENGTH)}...`
        : step.content;
    return (
      <details>
        <summary>
          <span className="step-label">Result</span>{" "}
          <code className="mono">{summary}</code>
        </summary>
        <pre className="step-result">{step.content}</pre>
      </details>
    );
  }
  const labels = { message: "Agent", read: "Read", error: "Failed" };
  return (
    <p>
      <span className="step-label">{labels[step.kind]}</span> {step.content}
    </p>
  );
}
