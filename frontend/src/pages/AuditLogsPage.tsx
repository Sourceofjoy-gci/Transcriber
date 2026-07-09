import { useMemo, useState } from "react";
import type { ReactElement } from "react";
import { useQuery } from "@tanstack/react-query";
import { listAuditLogs } from "../lib/api";
import type { AuditLog } from "../types";
import {
  EmptyState,
  ErrorBanner,
  LoadingScreen,
  PageHeader,
  relativeTime,
} from "../components/common";

const ACTION_FILTERS = [
  { value: "", label: "All actions" },
  { value: "auth.login", label: "Login" },
  { value: "auth.logout", label: "Logout" },
  { value: "auth.login_failed", label: "Failed login" },
  { value: "asset.uploaded", label: "Asset upload" },
  { value: "asset.deleted", label: "Asset deletion" },
  { value: "job.created", label: "Job created" },
  { value: "job.cancelled", label: "Job cancelled" },
  { value: "job.retried", label: "Job retried" },
  { value: "transcript.segment_edited", label: "Transcript edit" },
  { value: "transcript.version_restored", label: "Version restored" },
  { value: "export.created", label: "Export created" },
  { value: "report.created", label: "Report created" },
  { value: "model.downloaded", label: "Model downloaded" },
  { value: "provider.changed", label: "Provider change" },
  { value: "user.changed", label: "User change" },
];

export function AuditLogsPage(): ReactElement {
  const [action, setAction] = useState<string>("");
  const query = useQuery({
    queryKey: ["audit-logs", action],
    queryFn: () => listAuditLogs({ limit: 250 }),
  });

  const filtered = useMemo(() => {
    const items = query.data ?? [];
    if (!action) return items;
    return items.filter((log) => log.action.startsWith(action));
  }, [query.data, action]);

  return (
    <section className="space-y-6">
      <PageHeader
        eyebrow="Compliance"
        title="Audit Log"
        subtitle="Sensitive actions are recorded with timestamps, actor, target, and outcome."
      />

      <label className="field-label max-w-md">
        Action filter
        <select
          className="field-input"
          value={action}
          onChange={(e) => setAction(e.target.value)}
        >
          {ACTION_FILTERS.map((filter) => (
            <option key={filter.value} value={filter.value}>
              {filter.label}
            </option>
          ))}
        </select>
      </label>

      {query.isError && (
        <ErrorBanner
          message="Audit logs are temporarily unavailable."
          onRetry={() => query.refetch()}
        />
      )}

      {query.isLoading && <LoadingScreen message="Loading audit logs…" />}

      {!query.isLoading && filtered.length === 0 && (
        <EmptyState
          title="No matching audit entries"
          hint="Adjust the filter to broaden the search."
        />
      )}

      {filtered.length > 0 && (
        <div className="overflow-hidden rounded-2xl border border-emerald-950/10 bg-white shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">Time</th>
                <th className="px-4 py-3">Actor</th>
                <th className="px-4 py-3">Action</th>
                <th className="px-4 py-3">Target</th>
                <th className="px-4 py-3">Outcome</th>
                <th className="px-4 py-3">Data</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((log) => (
                <AuditRow key={log.id} log={log} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function AuditRow({ log }: { log: AuditLog }): ReactElement {
  return (
    <tr className="border-t border-slate-100 align-top">
      <td className="px-4 py-3 text-slate-600">
        {relativeTime(log.created_at)}
      </td>
      <td className="px-4 py-3 font-mono text-xs">
        {log.actor_id?.slice(0, 8) ?? "system"}
      </td>
      <td className="px-4 py-3 font-mono text-xs">{log.action}</td>
      <td className="px-4 py-3 text-xs text-slate-600">
        {log.resource_type}
        {log.resource_id && (
          <>
            :<span className="font-mono">{log.resource_id.slice(0, 8)}</span>
          </>
        )}
      </td>
      <td className="px-4 py-3">
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
            log.outcome === "success"
              ? "bg-emerald-100 text-emerald-800"
              : "bg-rose-100 text-rose-700"
          }`}
        >
          {log.outcome}
        </span>
      </td>
      <td className="px-4 py-3 font-mono text-xs text-slate-500">
        {Object.keys(log.data).length > 0 ? (
          <details>
            <summary className="cursor-pointer">view</summary>
            <pre className="mt-1 max-w-md overflow-x-auto whitespace-pre-wrap text-xs">
              {JSON.stringify(log.data, null, 2)}
            </pre>
          </details>
        ) : (
          "—"
        )}
      </td>
    </tr>
  );
}
