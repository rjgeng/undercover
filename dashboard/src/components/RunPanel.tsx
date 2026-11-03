import { api } from "../api";
import { time } from "../format";
import { REFRESH_MS, useLoad } from "../useLoad";
import { RunChip, TodoChip } from "./Chips";
import { Message } from "./Message";

export function RunPanel() {
  const { data: run, error } = useLoad(api.getLatestRun, REFRESH_MS);

  return (
    <section className="panel run" aria-labelledby="run-title">
      <h2 id="run-title">Agent run</h2>
      {run === undefined && <Message error={error} />}
      {run === null && <p className="muted">No runs yet.</p>}
      {run && (
        <>
          <div className="run-line">
            <span className="mono">{run.run_id}</span>
            <RunChip status={run.status} />
            <span className="small muted">
              Started {time(run.started_at)}, up to {run.cap}{" "}
              {run.cap === 1 ? "claim" : "claims"}
            </span>
          </div>
          {run.todos.length === 0 ? (
            <p className="muted">No to-do list yet.</p>
          ) : (
            <ol className="todos" aria-label="To-do list">
              {run.todos.map((todo) => (
                <li className="todo" key={todo.content}>
                  <TodoChip status={todo.status} />
                  <span>{todo.content}</span>
                </li>
              ))}
            </ol>
          )}
          {run.summary && <p className="run-summary">{run.summary}</p>}
        </>
      )}
    </section>
  );
}
