import type { ReactElement } from "react";
import { useQuery } from "@tanstack/react-query";
import { getDashboardMetrics } from "../lib/api";
import {
  ErrorBanner,
  LoadingScreen,
  formatBytes,
  formatDuration,
  relativeTime,
} from "../components/common";

export function DashboardPage(): ReactElement {
  const metricsQuery = useQuery({
    queryKey: ["dashboard"],
    queryFn: getDashboardMetrics,
    refetchInterval: 10000,
  });

  const metrics = metricsQuery.data;

  return (
    <section className="space-y-7">
      <div className="rounded-3xl bg-ink px-7 py-8 text-white shadow-lg shadow-emerald-950/20">
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-emerald-200">
          Local-first workspace
        </p>
        <h1 className="mt-3 max-w-2xl text-3xl font-bold tracking-tight sm:text-4xl">
          A calm place for demanding recordings.
        </h1>
        <p className="mt-3 max-w-2xl text-slate-300">
          Upload media, queue transcription, edit transcripts, and generate
          reports — all without leaving your network.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Media files"
          value={metrics?.total_files ?? "—"}
          note="Stored recordings"
        />
        <MetricCard
          label="In progress"
          value={metrics?.jobs_in_progress ?? "—"}
          note="Queued or processing"
        />
        <MetricCard
          label="Completed"
          value={metrics?.completed_transcriptions ?? "—"}
          note="Completed transcriptions"
        />
        <MetricCard
          label="Failed"
          value={metrics?.failed_transcriptions ?? "—"}
          note="Failed transcriptions"
        />
        <MetricCard
          label="Storage"
          value={metrics ? formatBytes(metrics.storage_bytes) : "—"}
          note="Private media storage"
        />
        <MetricCard
          label="Total transcription"
          value={
            metrics ? formatDuration(metrics.total_transcription_seconds) : "—"
          }
          note="Sum of audio length"
        />
        <MetricCard
          label="Average job time"
          value={
            metrics?.average_processing_ms !== undefined &&
            metrics.average_processing_ms !== null
              ? formatDuration(metrics.average_processing_ms / 1000)
              : "—"
          }
          note="Per completed transcription"
        />
        <MetricCard
          label="Estimated cost"
          value={metrics ? `$${metrics.api_cost_estimate.toFixed(4)}` : "$0.00"}
          note="External provider usage"
        />
      </div>

      {metricsQuery.isLoading && <LoadingScreen message="Loading dashboard…" />}
      {metricsQuery.isError && (
        <ErrorBanner
          message="Dashboard metrics are temporarily unavailable."
          onRetry={() => metricsQuery.refetch()}
        />
      )}

      {(metrics?.most_used_models?.length ?? 0) > 0 && (
        <article className="rounded-2xl border border-emerald-950/10 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-bold">Most used local models</h2>
          <ul className="mt-3 space-y-1 text-sm">
            {metrics!.most_used_models.map((model) => (
              <li
                key={model.installed_model_id}
                className="flex justify-between"
              >
                <span className="font-mono text-xs">
                  {model.installed_model_id.slice(0, 8)}
                </span>
                <span className="font-semibold">{model.count} jobs</span>
              </li>
            ))}
          </ul>
        </article>
      )}

      {(metrics?.most_used_providers?.length ?? 0) > 0 && (
        <article className="rounded-2xl border border-emerald-950/10 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-bold">Execution target distribution</h2>
          <ul className="mt-3 space-y-1 text-sm">
            {metrics!.most_used_providers.map((provider) => (
              <li key={provider.provider} className="flex justify-between">
                <span>{provider.provider.replaceAll("_", " ")}</span>
                <span className="font-semibold">{provider.count} jobs</span>
              </li>
            ))}
          </ul>
        </article>
      )}

      {(metrics?.recent_jobs?.length ?? 0) > 0 && (
        <article className="rounded-2xl border border-emerald-950/10 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-bold">Recent jobs</h2>
          <ul className="mt-3 space-y-1 text-sm">
            {metrics!.recent_jobs.map((job) => (
              <li
                key={job.id}
                className="flex flex-wrap items-center justify-between gap-2"
              >
                <span className="font-mono text-xs text-slate-600">
                  {job.id.slice(0, 8)}
                </span>
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs">
                  {job.status}
                </span>
                <span className="text-xs text-slate-500">
                  {relativeTime(job.created_at)}
                </span>
              </li>
            ))}
          </ul>
        </article>
      )}

      {(metrics?.recent_errors?.length ?? 0) > 0 && (
        <article className="rounded-2xl border border-rose-200 bg-rose-50 p-5 shadow-sm">
          <h2 className="text-lg font-bold text-rose-900">
            Recent errors (last 24h)
          </h2>
          <ul className="mt-3 space-y-1 text-sm text-rose-900">
            {metrics!.recent_errors.map((err) => (
              <li key={err.job_id}>
                <strong>{err.error_code ?? "error"}:</strong>{" "}
                {err.error_message ?? "—"}{" "}
                <span className="text-rose-700">
                  ({relativeTime(err.created_at)})
                </span>
              </li>
            ))}
          </ul>
        </article>
      )}
    </section>
  );
}

function MetricCard({
  label,
  value,
  note,
}: {
  label: string;
  value: string | number;
  note: string;
}): ReactElement {
  return (
    <article className="rounded-2xl border border-emerald-950/10 bg-white p-5 shadow-sm">
      <p className="text-sm font-medium text-slate-600">{label}</p>
      <p className="mt-2 text-3xl font-bold tracking-tight text-ink">{value}</p>
      <p className="mt-2 text-xs text-slate-500">{note}</p>
    </article>
  );
}
