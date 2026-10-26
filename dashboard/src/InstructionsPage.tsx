import { api } from "./api";
import { useApi } from "./useApi";

export function InstructionsPage() {
  const { data: instructions } = useApi(api.instructions, false);
  const { data: wording } = useApi(api.wording, false);
  return (
    <>
      <h1>The agent&apos;s instructions</h1>
      <p className="muted">
        Read only. The agent reads its instructions and the policy wording
        before every claim.
      </p>
      <div className="columns">
        <section className="panel" aria-label="Instructions">
          <pre className="text">{instructions?.text}</pre>
        </section>
        <section className="panel" aria-label="Policy wording">
          <h2>Policy wording, version {wording?.version}</h2>
          <pre className="text">{wording?.text}</pre>
        </section>
      </div>
    </>
  );
}
