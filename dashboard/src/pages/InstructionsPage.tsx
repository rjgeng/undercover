import { api } from "../api";
import { Message } from "../components/Message";
import { useLoad } from "../useLoad";

export function InstructionsPage() {
  const { data, error } = useLoad(api.getInstructions);

  return (
    <>
      <h1>Agent instructions</h1>
      <p className="lead">
        What the agent works from: its instructions for running the queue, and
        for working each claim, which end with the contents of the policy
        wording and the claims manual it looks sections up in. This page is read
        only.
      </p>
      {data ? (
        <div className="column">
          <section className="panel" aria-labelledby="queue-title">
            <h2 id="queue-title">Running the queue</h2>
            <pre className="instructions">{data.queue}</pre>
          </section>
          <section className="panel" aria-labelledby="claim-title">
            <h2 id="claim-title">Working a claim</h2>
            <pre className="instructions">{data.claim}</pre>
          </section>
        </div>
      ) : (
        <section className="panel">
          <Message error={error} />
        </section>
      )}
    </>
  );
}
