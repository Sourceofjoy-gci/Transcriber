import { useState } from "react";
import type { ReactElement } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  cancelJob,
  listJobAttempts,
  listJobEvents,
  listJobs,
  retryJob,
} from "../lib/api";
import type { TranscriptionJob } from "../types";
import {
  ConfirmDialog,
  EmptyState,
  ErrorBanner,
  LoadingScreen,
  Spinner,
  relativeTime,
} from "../components/common";

const STATUS_FILTERS = [
  { value: "", label: "All" },
  { value: "queued", label: "Queued" },
  { value: "extracting_audio", label: "Extracting" },
  { value: "transcribing", label: "Transcribing" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed" },
  { value: "cancelled", label: "Cancelled" },
];

export function JobsPage(): ReactElement {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [confirmCancel, setConfirmCancel] = useState<TranscriptionJob | null>(
    null,
  );
  const [confirmRetry, setConfirmRetry] = useState<TranscriptionJob | null>(
    null,
  );
  const [actionError, setActionError] = useState<string | null>(null);
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);

  const jobsQuery = useQuery({
    queryKey: ["jobs", { status: statusFilter }],
    queryFn: () => listJobs({ status: statusFilter || undefined }),
    refetchInterval: 4000,
  });

  const cancelMutation = useMutation({
    mutationFn: cancelJob,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      setConfirmCancel(null);
    },
    onError: (e) =>
      setActionError(e instanceof ApiError ? e.message : "Cancel failed"),
  });

  const retryMutation = useMutation({
    mutationFn: retryJob,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      setConfirmRetry(null);
    },
    onError: (e) =>
      setActionError(e instanceof ApiError ? e.message : "Retry failed"),
  });

  if (jobsQuery.isLoading) return <LoadingScreen message="Loading jobs…" />;

  const jobs = jobsQuery.data ?? [];

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="eyebrow">Queue</p>
          <h1 className="page-title">Transcription jobs</h1>
          <p className="page-subtitle">
            Live progress events, retry/cancel actions, and attempt history for
            every transcription job.
          </p>
        </div>
        <select
          className="field-input max-w-[200px]"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          aria-label="Filter jobs by status"
        >
          {STATUS_FILTERS.map((filter) => (
            <option key={filter.value} value={filter.value}>
              {filter.label}
            </option>
          ))}
        </select>
      </div>

      {actionError && (
        <ErrorBanner
          message={actionError}
          onRetry={() => setActionError(null)}
        />
      )}

      {!jobs.length && !jobsQuery.isLoading && (
        <EmptyState
          title="No transcription jobs match this filter"
          hint="Adjust the filter or upload media to create a new job."
        />
      )}

      <div className="overflow-hidden rounded-2xl border border-emerald-950/10 bg-white shadow-sm">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-5 py-4">Job</th>
              <th className="px-5 py-4">Status</th>
              <th className="px-5 py-4">Progress</th>
              <th className="px-5 py-4">Created</th>
              <th className="px-5 py-4">Actions</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.id} className="border-t border-slate-100 align-top">
                <td className="px-5 py-4">
                  <button
                    type="button"
                    className="text-left font-mono text-xs font-semibold text-fern hover:underline"
                    onClick={() =>
                      setExpandedJobId(expandedJobId === job.id ? null : job.id)
                    }
                  >
                    {job.id.slice(0, 8)}
                  </button>
                  <p className="mt-1 text-xs text-slate-500">
                    {job.execution_target_kind.replaceAll("_", " ")}
                    {job.error_message && (
                      <span className="mt-1 block text-rose-700">
                        {job.error_message}
                      </span>
                    )}
                  </p>
                  {expandedJobId === job.id && <JobDetails jobId={job.id} />}
                </td>
                <td className="px-5 py-4">
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                      job.status === "completed"
                        ? "bg-emerald-100 text-emerald-800"
                        : job.status === "failed"
                          ? "bg-rose-100 text-rose-700"
                          : job.status === "cancelled"
                            ? "bg-slate-200 text-slate-700"
                            : "bg-amber-100 text-amber-800"
                    }`}
                  >
                    {job.status.replaceAll("_", " ")}
                  </span>
                </td>
                <td className="px-5 py-4">
                  <div className="flex items-center gap-2">
                    <div className="h-2 w-24 overflow-hidden rounded-full bg-slate-100">
                      <div
                        className="h-full bg-fern transition-all"
                        style={{ width: `${job.progress_percent}%` }}
                      />
                    </div>
                    <span className="text-xs font-semibold">
                      {job.progress_percent}%
                    </span>
                  </div>
                </td>
                <td className="px-5 py-4 text-slate-600">
                  {relativeTime(job.created_at)}
                </td>
                <td className="px-5 py-4">
                  <div className="flex flex-wrap gap-2">
                    {(job.status === "queued" ||
                      job.status === "extracting_audio" ||
                      job.status === "transcribing" ||
                      job.status === "preprocessing" ||
                      job.status === "post_processing") && (
                      <button
                        type="button"
                        className="button-secondary !text-rose-700"
                        onClick={() => setConfirmCancel(job)}
                      >
                        Cancel
                      </button>
                    )}
                    {(job.status === "failed" ||
                      job.status === "cancelled") && (
                      <button
                        type="button"
                        className="button-primary"
                        onClick={() => setConfirmRetry(job)}
                      >
                        Retry
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ConfirmDialog
        open={Boolean(confirmCancel)}
        title="Cancel transcription job?"
        message="The worker will stop processing. Already transcribed segments will be preserved."
        destructive
        confirmLabel="Cancel job"
        onConfirm={() =>
          confirmCancel && cancelMutation.mutate(confirmCancel.id)
        }
        onCancel={() => setConfirmCancel(null)}
      />
      <ConfirmDialog
        open={Boolean(confirmRetry)}
        title="Retry transcription job?"
        message="The job will be re-queued. Prior attempt history is preserved for diagnostics."
        confirmLabel="Retry"
        onConfirm={() => confirmRetry && retryMutation.mutate(confirmRetry.id)}
        onCancel={() => setConfirmRetry(null)}
      />
    </section>
  );
}

function JobDetails({ jobId }: { jobId: string }): ReactElement {
  const attemptsQuery = useQuery({
    queryKey: ["job-attempts", jobId],
    queryFn: () => listJobAttempts(jobId),
  });
  const eventsQuery = useQuery({
    queryKey: ["job-events", jobId],
    queryFn: () => listJobEvents(jobId),
    refetchInterval: 3000,
  });
  return (
    <div className="mt-3 space-y-3 rounded-lg bg-slate-50 p-3 text-xs">
      <div>
        <p className="font-semibold uppercase tracking-wide text-slate-500">
          Attempts
        </p>
        {attemptsQuery.isLoading ? (
          <p>Loading…</p>
        ) : attemptsQuery.data && attemptsQuery.data.length > 0 ? (
          <ul className="mt-1 space-y-1">
            {attemptsQuery.data.map((attempt) => (
              <li key={attempt.id}>
                #{attempt.attempt_number} · {attempt.status} ·{" "}
                {relativeTime(attempt.started_at)} →{" "}
                {relativeTime(attempt.finished_at)}
                {attempt.error_detail && (
                  <span className="block text-rose-700">
                    {attempt.error_detail}
                  </span>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-slate-500">No attempts recorded yet.</p>
        )}
      </div>
      <div>
        <p className="font-semibold uppercase tracking-wide text-slate-500">
          Recent events
        </p>
        {eventsQuery.isLoading ? (
          <p>Loading…</p>
        ) : (
          <ul className="mt-1 space-y-1">
            {(eventsQuery.data ?? []).slice(-5).map((event) => (
              <li key={event.id}>
                {relativeTime(event.created_at)} · {event.state} ·{" "}
                {event.progress_percent}% · {event.message}
              </li>
            ))}
            {eventsQuery.isFetching && (
              <li>
                <Spinner /> refreshing…
              </li>
            )}
          </ul>
        )}
      </div>
    </div>
  );
}
