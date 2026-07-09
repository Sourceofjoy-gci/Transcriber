import { useState } from "react";
import type { ReactElement } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createAssetDownloadUrl,
  deleteAsset,
  listAssets,
  listProjects,
} from "../lib/api";
import {
  ErrorBanner,
  formatBytes,
  formatDuration,
  LoadingScreen,
  PageHeader,
  Spinner,
} from "../components/common";

export function AssetsPage(): ReactElement {
  const queryClient = useQueryClient();
  const [projectId, setProjectId] = useState("");
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState("");
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const projectsQuery = useQuery({
    queryKey: ["projects"],
    queryFn: listProjects,
  });
  const assetsQuery = useQuery({
    queryKey: ["assets", projectId, status, query],
    queryFn: () =>
      listAssets({
        project_id: projectId || undefined,
        status: status || undefined,
        q: query || undefined,
      }),
  });
  const downloadMutation = useMutation({
    mutationFn: createAssetDownloadUrl,
    onSuccess: (result) => {
      setDownloadUrl(result.url);
    },
    onError: (error) =>
      setActionError(
        error instanceof Error ? error.message : "Download failed",
      ),
  });
  const deleteMutation = useMutation({
    mutationFn: deleteAsset,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["assets"] }),
    onError: (error) =>
      setActionError(error instanceof Error ? error.message : "Delete failed"),
  });

  if (assetsQuery.isLoading)
    return <LoadingScreen message="Loading assets..." />;

  const projects = projectsQuery.data ?? [];
  const projectName = new Map(
    projects.map((project) => [project.id, project.name] as const),
  );

  return (
    <section className="space-y-6">
      <PageHeader
        eyebrow="Archive"
        title="Asset Library"
        subtitle="Browse uploaded media by project, status, and metadata."
      />
      {actionError && (
        <ErrorBanner
          message={actionError}
          onRetry={() => setActionError(null)}
        />
      )}
      {downloadUrl && (
        <a className="button-primary" href={downloadUrl}>
          Download ready
        </a>
      )}
      <article className="rounded-2xl border border-emerald-950/10 bg-white p-5 shadow-sm">
        <div className="grid gap-3 md:grid-cols-3">
          <label className="field-label">
            Project
            <select
              className="field-input"
              value={projectId}
              onChange={(event) => setProjectId(event.target.value)}
            >
              <option value="">All projects</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field-label">
            Status
            <select
              className="field-input"
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="">Any status</option>
              <option value="ready">Ready</option>
              <option value="failed">Failed</option>
              <option value="processing_metadata">Processing metadata</option>
            </select>
          </label>
          <label className="field-label">
            Search
            <input
              className="field-input"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
        </div>
      </article>
      <div className="grid gap-3">
        {(assetsQuery.data?.items ?? []).map((asset) => (
          <article
            key={asset.id}
            className="rounded-2xl border border-emerald-950/10 bg-white p-5 shadow-sm"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="font-semibold text-ink">
                  {asset.original_filename}
                </h2>
                <p className="mt-1 text-sm text-slate-600">
                  {projectName.get(asset.project_id ?? "") ?? "No project"} ·{" "}
                  {asset.status.replaceAll("_", " ")} ·{" "}
                  {formatBytes(asset.byte_size)}
                </p>
                {asset.metadata && (
                  <p className="mt-1 text-xs text-slate-500">
                    {asset.metadata.container ?? asset.content_type} ·{" "}
                    {asset.metadata.duration_ms
                      ? formatDuration(asset.metadata.duration_ms / 1000)
                      : "Duration pending"}
                  </p>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="button-secondary"
                  onClick={() => downloadMutation.mutate(asset.id)}
                >
                  {downloadMutation.isPending ? <Spinner /> : "Download"}
                </button>
                <button
                  type="button"
                  className="button-secondary !text-rose-700"
                  onClick={() => deleteMutation.mutate(asset.id)}
                >
                  Delete
                </button>
              </div>
            </div>
          </article>
        ))}
        {assetsQuery.data?.items.length === 0 && (
          <p className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
            No assets match these filters.
          </p>
        )}
      </div>
    </section>
  );
}
