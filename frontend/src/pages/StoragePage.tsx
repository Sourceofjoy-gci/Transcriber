import type { ReactElement } from "react";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getStorageOverview, purgeExpiredStorage } from "../lib/api";
import {
  ErrorBanner,
  Info,
  LoadingScreen,
  PageHeader,
  Spinner,
  formatBytes,
} from "../components/common";

export function StoragePage(): ReactElement {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<string | null>(null);
  const overviewQuery = useQuery({
    queryKey: ["storage-overview"],
    queryFn: getStorageOverview,
    refetchInterval: 10000,
  });
  const purgeMutation = useMutation({
    mutationFn: purgeExpiredStorage,
    onSuccess: (result) => {
      setMessage(
        `${result.purged_assets} asset${result.purged_assets === 1 ? "" : "s"} purged; ${result.deleted_objects} object${result.deleted_objects === 1 ? "" : "s"} deleted.`,
      );
      queryClient.invalidateQueries({ queryKey: ["storage-overview"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["assets"] });
    },
    onError: () => setMessage("Retention purge failed."),
  });

  const overview = overviewQuery.data;

  return (
    <section className="space-y-6">
      <PageHeader
        eyebrow="Operations"
        title="Storage"
        subtitle="Monitor private media usage, derivative storage, retention state, and provider health."
        actions={
          <button
            type="button"
            className="button-primary"
            onClick={() => purgeMutation.mutate()}
            disabled={purgeMutation.isPending}
          >
            {purgeMutation.isPending ? <Spinner /> : "Purge expired"}
          </button>
        }
      />

      {overviewQuery.isLoading && (
        <LoadingScreen message="Loading storage state..." />
      )}
      {overviewQuery.isError && (
        <ErrorBanner
          message="Storage overview is unavailable."
          onRetry={() => overviewQuery.refetch()}
        />
      )}
      {message && (
        <p className="rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          {message}
        </p>
      )}

      {overview && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label="Total storage"
              value={formatBytes(overview.storage_bytes)}
              note="Originals and derivatives"
            />
            <MetricCard
              label="Original media"
              value={formatBytes(overview.original_bytes)}
              note="Active, non-deleted media"
            />
            <MetricCard
              label="Derivatives"
              value={formatBytes(overview.derivative_bytes)}
              note="Waveforms, normalized audio, thumbnails"
            />
            <MetricCard
              label="Retention"
              value={
                overview.retention_days
                  ? `${overview.retention_days} days`
                  : "Default"
              }
              note="Organisation policy"
            />
          </div>

          <article className="rounded-2xl border border-emerald-950/10 bg-white p-5 shadow-sm">
            <h2 className="text-lg font-bold">Provider health</h2>
            <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Info
                label="Provider"
                value={overview.provider.replaceAll("_", " ")}
              />
              <Info
                label="Status"
                value={overview.healthy ? "Healthy" : "Unavailable"}
              />
              <Info label="Active assets" value={overview.active_assets} />
              <Info
                label="Deleted pending purge"
                value={overview.deleted_assets}
              />
              <Info label="Legal holds" value={overview.legal_hold_assets} />
            </div>
          </article>
        </>
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
  value: string;
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
