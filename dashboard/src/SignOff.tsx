import { useState, type SyntheticEvent } from "react";
import { api, type Claim, type Handler } from "./api";
import { money } from "./format";

export function SignOff({
  claim,
  handlers,
  onDone,
}: Readonly<{ claim: Claim; handlers: Handler[]; onDone: () => void }>) {
  const [handlerId, setHandlerId] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  const submit = (event: SyntheticEvent) => {
    event.preventDefault();
    setBusy(true);
    void api
      .signOff(claim.claim_id, handlerId)
      .then(onDone, (reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "Failed");
      })
      .finally(() => {
        setBusy(false);
      });
  };

  return (
    <form className="sign-off" aria-label="Sign off" onSubmit={submit}>
      <label>
        Handler{" "}
        <select
          value={handlerId}
          onChange={(event) => {
            setHandlerId(event.target.value);
          }}
        >
          <option value="">Choose a handler</option>
          {handlers
            .filter((handler) => handler.can_approve_over_limit)
            .map((handler) => (
              <option key={handler.handler_id} value={handler.handler_id}>
                {handler.name}
              </option>
            ))}
        </select>
      </label>
      <button type="submit" disabled={!handlerId || busy}>
        Sign off and pay {money(claim.payout ?? 0)}
      </button>
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}
