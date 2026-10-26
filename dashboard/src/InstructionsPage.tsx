import { api } from "./api";
import { Pending } from "./Pending";
import { useApi } from "./useApi";

export function InstructionsPage() {
  const instructions = useApi(api.instructions, false);
  const wording = useApi(api.wording, false);
  return (
    <>
      <h1>The agent&apos;s instructions</h1>
      <p className="muted">
        Read only. The agent reads its instructions and the policy wording
        before every claim.
      </p>
      <div className="columns">
        <section className="panel" aria-label="Instructions">
          {instructions.data ? (
            <pre className="text">{instructions.data.text}</pre>
          ) : (
            <Pending error={instructions.error} />
          )}
        </section>
        <section className="panel" aria-label="Policy wording">
          {wording.data ? (
            <>
              <h2>Policy wording, version {wording.data.version}</h2>
              <pre className="text">{wording.data.text}</pre>
            </>
          ) : (
            <Pending error={wording.error} />
          )}
        </section>
      </div>
    </>
  );
}
