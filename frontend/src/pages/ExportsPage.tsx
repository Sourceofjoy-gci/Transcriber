import type { ReactElement } from "react";
import { useQuery } from "@tanstack/react-query";
import { exportDownloadUrl, listExports } from "../lib/api";
import {
  EmptyState,
  ErrorBanner,
  LoadingScreen,
  PageHeader,
  relativeTime,
} from "../components/common";

export function ExportsPage(): ReactElement {
  const query = useQuery({
    queryKey: ["exports"],
    queryFn: listExports,
    refetchInterval: 5000,
  });
  return (
    <section className="space-y-6">
      <PageHeader
        eyebrow="Archive"
        title="Exports"
        subtitle="Download previously generated transcripts in any supported format."
      />
      {query.isError && <ErrorBanner message="Exports list unavailable." />}
      {query.isLoading && <LoadingScreen message="Loading exports…" />}
      {!query.isLoading && !query.data?.length && (
        <EmptyState
          title="No exports yet"
          hint="Open a transcript and request an export to see it listed here."
        />
      )}
      {query.data && query.data.length > 0 && (
        <div className="overflow-hidden rounded-2xl border border-emerald-950/10 bg-white shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">Format</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Created</th>
                <th className="px-4 py-3">Expires</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {query.data.map((exp) => (
                <tr
                  key={exp.id}
                  className="border-t border-slate-100 align-top"
                >
                  <td className="px-4 py-3 font-mono text-xs uppercase">
                    {exp.format}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                        exp.status === "completed"
                          ? "bg-emerald-100 text-emerald-800"
                          : exp.status === "failed"
                            ? "bg-rose-100 text-rose-700"
                            : "bg-amber-100 text-amber-800"
                      }`}
                    >
                      {exp.status}
                    </span>
                    {exp.error_message && (
                      <p className="mt-1 text-xs text-rose-700">
                        {exp.error_message}
                      </p>
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-600">
                    {relativeTime(exp.created_at)}
                  </td>
                  <td className="px-4 py-3 text-slate-600">
                    {relativeTime(exp.expires_at)}
                  </td>
                  <td className="px-4 py-3">
                    {exp.status === "completed" && (
                      <a
                        className="button-primary"
                        href={exportDownloadUrl(exp.id)}
                      >
                        Download
                      </a>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
