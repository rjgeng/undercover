import type { Status } from "./api";
import { STATUS_LABELS } from "./format";

export function StatusBadge({ status }: Readonly<{ status: Status }>) {
  return <span className={`badge ${status}`}>{STATUS_LABELS[status]}</span>;
}
