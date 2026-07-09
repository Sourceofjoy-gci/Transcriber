import type { AssetStatus, JobStatus } from "../types";

const colorByStatus: Record<AssetStatus | JobStatus, string> = {
  uploading: "bg-sky-100 text-sky-800",
  uploaded: "bg-sky-100 text-sky-800",
  processing_metadata: "bg-amber-100 text-amber-800",
  ready: "bg-emerald-100 text-emerald-800",
  queued: "bg-slate-200 text-slate-700",
  extracting_audio: "bg-amber-100 text-amber-800",
  preprocessing: "bg-amber-100 text-amber-800",
  transcribing: "bg-violet-100 text-violet-800",
  post_processing: "bg-violet-100 text-violet-800",
  completed: "bg-emerald-100 text-emerald-800",
  failed: "bg-rose-100 text-rose-800",
  cancelled: "bg-slate-200 text-slate-700",
  deleted: "bg-slate-200 text-slate-700",
};

export function StatusBadge({
  status,
}: {
  status: AssetStatus | JobStatus;
}): JSX.Element {
  return (
    <span
      className={`rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${colorByStatus[status]}`}
    >
      {status.replaceAll("_", " ")}
    </span>
  );
}
