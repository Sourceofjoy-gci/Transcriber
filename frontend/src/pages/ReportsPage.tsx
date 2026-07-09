import { useMemo, useState } from "react";
import type { ReactElement } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  createExport,
  createReport,
  deleteReport,
  getReport,
  listReportTemplates,
  listReports,
  listTranscripts,
  updateReport,
} from "../lib/api";
import type { Report } from "../types";
import {
  ConfirmDialog,
  EmptyState,
  ErrorBanner,
  LoadingScreen,
  PageHeader,
  Spinner,
  relativeTime,
} from "../components/common";

export function ReportsPage(): ReactElement {
  const queryClient = useQueryClient();
  const reportsQuery = useQuery({
    queryKey: ["reports"],
    queryFn: listReports,
  });
  const templatesQuery = useQuery({
    queryKey: ["report-templates"],
    queryFn: listReportTemplates,
  });
  const transcriptsQuery = useQuery({
    queryKey: ["transcripts"],
    queryFn: () => listTranscripts({ limit: 100 }),
  });
  const [showForm, setShowForm] = useState(false);
  const [templateId, setTemplateId] = useState<string>("");
  const [transcriptId, setTranscriptId] = useState<string>("");
  const [title, setTitle] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [selectedReport, setSelectedReport] = useState<Report | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<Report | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: createReport,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reports"] });
      setShowForm(false);
      setTitle("");
      setTemplateId("");
      setTranscriptId("");
      setFormError(null);
    },
    onError: (e) =>
      setFormError(
        e instanceof ApiError ? e.message : "Failed to create report",
      ),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteReport,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reports"] });
      setConfirmDelete(null);
      setSelectedReport(null);
    },
    onError: (e) =>
      setActionError(e instanceof ApiError ? e.message : "Delete failed"),
  });

  const sortedTemplates = useMemo(() => {
    const list = templatesQuery.data ?? [];
    return [...list].sort((a, b) => a.name.localeCompare(b.name));
  }, [templatesQuery.data]);

  function handleSubmit(event: React.FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (!templateId || !transcriptId || !title.trim()) {
      setFormError("Template, transcript, and title are required");
      return;
    }
    setFormError(null);
    createMutation.mutate({
      template_id: templateId,
      transcript_id: transcriptId,
      title: title.trim(),
    });
  }

  if (reportsQuery.isLoading)
    return <LoadingScreen message="Loading reports…" />;

  return (
    <section className="space-y-6">
      <PageHeader
        eyebrow="Intelligence"
        title="Reports"
        subtitle="Generate presentation reports, meeting minutes, and structured analyses from completed transcripts."
        actions={
          <button
            type="button"
            className="button-primary"
            onClick={() => setShowForm((v) => !v)}
          >
            {showForm ? "Cancel" : "New report"}
          </button>
        }
      />

      {actionError && (
        <ErrorBanner
          message={actionError}
          onRetry={() => setActionError(null)}
        />
      )}

      {showForm && (
        <article className="rounded-2xl border border-emerald-950/10 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-bold">Generate a new report</h2>
          <form
            className="mt-4 grid gap-4 sm:grid-cols-2"
            onSubmit={handleSubmit}
          >
            <label className="field-label">
              Template
              <select
                className="field-input"
                value={templateId}
                onChange={(e) => setTemplateId(e.target.value)}
                required
              >
                <option value="">Select a template…</option>
                {sortedTemplates.map((template) => (
                  <option key={template.id} value={template.id}>
                    {template.name}
                  </option>
                ))}
              </select>
              {templateId &&
                sortedTemplates.find((t) => t.id === templateId)
                  ?.description && (
                  <span className="text-xs text-slate-500">
                    {
                      sortedTemplates.find((t) => t.id === templateId)
                        ?.description
                    }
                  </span>
                )}
            </label>
            <label className="field-label">
              Transcript
              <select
                className="field-input"
                value={transcriptId}
                onChange={(e) => setTranscriptId(e.target.value)}
                required
              >
                <option value="">Select a transcript…</option>
                {transcriptsQuery.data?.map((transcript) => (
                  <option key={transcript.id} value={transcript.id}>
                    Transcript {transcript.id.slice(0, 8)} ·{" "}
                    {transcript.detected_language ?? "auto"}
                  </option>
                ))}
              </select>
            </label>
            <label className="field-label sm:col-span-2">
              Report title
              <input
                className="field-input"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Q2 stakeholder review"
                required
              />
            </label>
            {formError && (
              <p className="sm:col-span-2 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">
                {formError}
              </p>
            )}
            <div className="sm:col-span-2 flex gap-2">
              <button
                type="submit"
                className="button-primary"
                disabled={createMutation.isPending}
              >
                {createMutation.isPending ? <Spinner /> : "Queue report"}
              </button>
              <button
                type="button"
                className="button-secondary"
                onClick={() => {
                  setShowForm(false);
                  setFormError(null);
                }}
              >
                Cancel
              </button>
            </div>
          </form>
        </article>
      )}

      {!reportsQuery.data?.length && !showForm && (
        <EmptyState
          title="No reports generated yet"
          hint="Reports are produced from completed transcripts using one of the eight built-in templates."
        />
      )}

      <div className="grid gap-3">
        {reportsQuery.data?.map((report) => (
          <article
            key={report.id}
            className="rounded-2xl border border-emerald-950/10 bg-white p-5 shadow-sm transition hover:border-emerald-700/30"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <h3 className="font-semibold text-ink">{report.title}</h3>
                <p className="mt-1 text-sm text-slate-600">
                  {report.status === "completed" ? "Completed" : report.status}{" "}
                  · created {relativeTime(report.created_at)}
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  className="button-secondary"
                  onClick={() => setSelectedReport(report)}
                  disabled={report.status !== "completed"}
                >
                  View
                </button>
                <button
                  type="button"
                  className="button-secondary !text-rose-700"
                  onClick={() => setConfirmDelete(report)}
                >
                  Delete
                </button>
              </div>
            </div>
            {report.status === "failed" && report.error_message && (
              <p className="mt-2 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">
                {report.error_message}
              </p>
            )}
          </article>
        ))}
      </div>

      {selectedReport && (
        <ReportViewer
          report={selectedReport}
          onClose={() => setSelectedReport(null)}
        />
      )}

      <ConfirmDialog
        open={Boolean(confirmDelete)}
        title="Delete report?"
        message="The report content will be removed. Source transcripts are unaffected."
        destructive
        confirmLabel="Delete"
        onConfirm={() =>
          confirmDelete && deleteMutation.mutate(confirmDelete.id)
        }
        onCancel={() => setConfirmDelete(null)}
      />
    </section>
  );
}

function ReportViewer({
  report,
  onClose,
}: {
  report: Report;
  onClose: () => void;
}): ReactElement {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["report", report.id],
    queryFn: () => getReport(report.id),
  });
  const live = query.data ?? report;
  const [isEditing, setIsEditing] = useState(false);
  const [titleDraft, setTitleDraft] = useState(report.title);
  const [contentDraft, setContentDraft] = useState(
    JSON.stringify(report.content, null, 2),
  );
  const [message, setMessage] = useState<string | null>(null);
  const [editError, setEditError] = useState<string | null>(null);

  const updateMutation = useMutation({
    mutationFn: () => {
      let content: Record<string, unknown>;
      try {
        content = JSON.parse(contentDraft) as Record<string, unknown>;
      } catch {
        throw new Error("Report content must be valid JSON");
      }
      return updateReport(live.id, { title: titleDraft.trim(), content });
    },
    onSuccess: (updated) => {
      queryClient.setQueryData(["report", report.id], updated);
      queryClient.invalidateQueries({ queryKey: ["reports"] });
      setIsEditing(false);
      setEditError(null);
    },
    onError: (e) =>
      setEditError(e instanceof Error ? e.message : "Report update failed"),
  });

  const exportMutation = useMutation({
    mutationFn: () =>
      createExport({
        source_type: "report",
        report_id: live.id,
        format: "md",
        options: {},
      }),
    onSuccess: (exportRecord) => {
      setMessage(
        `${exportRecord.format.toUpperCase()} export ${exportRecord.status}.`,
      );
      queryClient.invalidateQueries({ queryKey: ["exports"] });
    },
    onError: (e) =>
      setMessage(e instanceof ApiError ? e.message : "Report export failed"),
  });

  function startEditing(): void {
    setTitleDraft(live.title);
    setContentDraft(JSON.stringify(live.content, null, 2));
    setEditError(null);
    setIsEditing(true);
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-40 grid place-items-center bg-slate-900/50 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-2xl bg-white p-6 shadow-xl">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-2xl font-bold text-ink">{live.title}</h2>
            <p className="mt-1 text-sm text-slate-600">
              {live.status} · created {relativeTime(live.created_at)}
            </p>
          </div>
          <button type="button" className="button-secondary" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="mt-5 space-y-4">
          {query.isLoading && <LoadingScreen message="Loading report…" />}
          {message && (
            <p className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
              {message}
            </p>
          )}
          {editError && (
            <ErrorBanner
              message={editError}
              onRetry={() => setEditError(null)}
            />
          )}
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="button-secondary"
              onClick={startEditing}
            >
              Edit
            </button>
            <button
              type="button"
              className="button-secondary"
              disabled={exportMutation.isPending}
              onClick={() => exportMutation.mutate()}
            >
              Export MD
            </button>
          </div>
          {isEditing ? (
            <div className="space-y-3">
              <label className="field-label">
                Report title
                <input
                  className="field-input"
                  value={titleDraft}
                  onChange={(event) => setTitleDraft(event.target.value)}
                />
              </label>
              <label className="field-label">
                Report content
                <textarea
                  className="field-input min-h-72 font-mono text-xs"
                  value={contentDraft}
                  onChange={(event) => setContentDraft(event.target.value)}
                />
              </label>
              <div className="flex gap-2">
                <button
                  type="button"
                  className="button-primary"
                  disabled={updateMutation.isPending}
                  onClick={() => updateMutation.mutate()}
                >
                  Save report
                </button>
                <button
                  type="button"
                  className="button-secondary"
                  onClick={() => setIsEditing(false)}
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            live.content && renderReportContent(live.content)
          )}
          {live.status === "failed" && live.error_message && (
            <div className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">
              {live.error_message}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function renderReportContent(content: Record<string, unknown>): ReactElement {
  const sections = Array.isArray(content.sections)
    ? (content.sections as Array<{ heading: string; body: string }>)
    : [];
  return (
    <div className="space-y-4">
      {typeof content.summary === "string" && content.summary && (
        <section className="rounded-xl bg-emerald-50 p-4">
          <h3 className="text-sm font-bold uppercase tracking-wide text-emerald-800">
            Executive summary
          </h3>
          <p className="mt-2 text-sm leading-6 text-slate-800">
            {content.summary}
          </p>
        </section>
      )}
      {sections.map((section) => (
        <section key={section.heading}>
          <h3 className="text-sm font-bold uppercase tracking-wide text-slate-700">
            {section.heading}
          </h3>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-800">
            {section.body}
          </p>
        </section>
      ))}
      {!sections.length && !content.summary && (
        <pre className="overflow-x-auto rounded-lg bg-slate-50 p-3 text-xs text-slate-700">
          {JSON.stringify(content, null, 2)}
        </pre>
      )}
    </div>
  );
}
