import { useMemo, useState } from "react";
import type { ReactElement } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  ApiError,
  createReportTemplate,
  deleteReportTemplate,
  disableReportTemplate,
  enableReportTemplate,
  listReportTemplates,
  previewReportTemplate,
} from "../lib/api";
import type { ReportTemplate } from "../types";
import type { ReportTemplateInput } from "../types";
import {
  EmptyState,
  ErrorBanner,
  LoadingScreen,
  PageHeader,
  Spinner,
} from "../components/common";

export function ReportTemplatesPage(): ReactElement {
  const queryClient = useQueryClient();
  const templatesQuery = useQuery({
    queryKey: ["report-templates"],
    queryFn: listReportTemplates,
  });
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [kind, setKind] = useState("");
  const [sectionsText, setSectionsText] = useState("");
  const [promptTemplate, setPromptTemplate] = useState("");
  const [previewTranscriptId, setPreviewTranscriptId] = useState("");
  const [previewContent, setPreviewContent] = useState<Record<
    string,
    unknown
  > | null>(null);
  const [error, setError] = useState<string | null>(null);

  const templates = useMemo(
    () =>
      [...(templatesQuery.data ?? [])].sort((a, b) =>
        a.name.localeCompare(b.name),
      ),
    [templatesQuery.data],
  );

  const createMutation = useMutation({
    mutationFn: (payload: ReportTemplateInput) => createReportTemplate(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["report-templates"] });
      setName("");
      setKind("");
      setSectionsText("");
      setPromptTemplate("");
      setShowForm(false);
      setError(null);
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : "Template creation failed"),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      enabled ? enableReportTemplate(id) : disableReportTemplate(id),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["report-templates"] }),
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : "Template update failed"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteReportTemplate(id),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["report-templates"] }),
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : "Template delete failed"),
  });

  const previewMutation = useMutation({
    mutationFn: (templateId: string) =>
      previewReportTemplate(templateId, {
        transcript_id: previewTranscriptId.trim(),
        title: "Template preview",
      }),
    onSuccess: (result) => {
      setPreviewContent(result.content);
      setError(null);
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : "Template preview failed"),
  });

  function handleCreate(event: React.FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const sections = sectionsText
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    if (!name.trim() || !kind.trim() || sections.length === 0) {
      setError("Template name, kind, and at least one section are required");
      return;
    }
    createMutation.mutate({
      name: name.trim(),
      kind: kind.trim(),
      schema: { sections },
      prompt_template: promptTemplate,
    });
  }

  if (templatesQuery.isLoading)
    return <LoadingScreen message="Loading report templates..." />;

  return (
    <section className="space-y-6">
      <PageHeader
        eyebrow="Reports"
        title="Report Templates"
        subtitle="Manage the structured section sets used when reports are generated from transcripts."
        actions={
          <button
            type="button"
            className="button-primary"
            onClick={() => setShowForm((value) => !value)}
          >
            {showForm ? "Cancel" : "New template"}
          </button>
        }
      />

      {error && <ErrorBanner message={error} onRetry={() => setError(null)} />}

      {showForm && (
        <article className="rounded-2xl border border-emerald-950/10 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-bold">Create template</h2>
          <form
            className="mt-4 grid gap-4 sm:grid-cols-2"
            onSubmit={handleCreate}
          >
            <label className="field-label">
              Template name
              <input
                aria-label="Template name"
                className="field-input"
                value={name}
                onChange={(event) => setName(event.target.value)}
                onInput={(event) => setName(event.currentTarget.value)}
              />
            </label>
            <label className="field-label">
              Kind
              <input
                aria-label="Kind"
                className="field-input"
                value={kind}
                onChange={(event) => setKind(event.target.value)}
                onInput={(event) => setKind(event.currentTarget.value)}
              />
            </label>
            <label className="field-label sm:col-span-2">
              Sections
              <textarea
                aria-label="Sections"
                className="field-input min-h-28"
                value={sectionsText}
                onChange={(event) => setSectionsText(event.target.value)}
                onInput={(event) => setSectionsText(event.currentTarget.value)}
              />
            </label>
            <label className="field-label sm:col-span-2">
              Prompt template
              <textarea
                className="field-input min-h-20"
                value={promptTemplate}
                onChange={(event) => setPromptTemplate(event.target.value)}
              />
            </label>
            <button
              type="submit"
              className="button-primary sm:col-span-2"
              disabled={createMutation.isPending}
            >
              {createMutation.isPending ? <Spinner /> : "Create template"}
            </button>
          </form>
        </article>
      )}

      <article className="rounded-2xl border border-emerald-950/10 bg-white p-5 shadow-sm">
        <label className="field-label max-w-xl">
          Preview transcript ID
          <input
            aria-label="Preview transcript ID"
            className="field-input"
            value={previewTranscriptId}
            onChange={(event) => setPreviewTranscriptId(event.target.value)}
            onInput={(event) =>
              setPreviewTranscriptId(event.currentTarget.value)
            }
          />
        </label>
      </article>

      {!templates.length && <EmptyState title="No report templates found" />}

      <div className="grid gap-3">
        {templates.map((template) => (
          <TemplateRow
            key={template.id}
            template={template}
            canPreview={previewTranscriptId.trim().length > 0}
            onToggle={() =>
              updateMutation.mutate({
                id: template.id,
                enabled: !template.enabled,
              })
            }
            onDelete={() => deleteMutation.mutate(template.id)}
            onPreview={() => previewMutation.mutate(template.id)}
          />
        ))}
      </div>

      {previewContent && (
        <article className="rounded-2xl border border-emerald-950/10 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-bold">Preview</h2>
          <div className="mt-3 space-y-3">
            {previewSections(previewContent).map((section) => (
              <section key={section.heading}>
                <h3 className="text-sm font-bold uppercase tracking-wide text-slate-600">
                  {section.heading}
                </h3>
                <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-slate-800">
                  {section.body}
                </p>
              </section>
            ))}
          </div>
        </article>
      )}
    </section>
  );
}

function TemplateRow({
  template,
  canPreview,
  onToggle,
  onDelete,
  onPreview,
}: {
  template: ReportTemplate;
  canPreview: boolean;
  onToggle: () => void;
  onDelete: () => void;
  onPreview: () => void;
}): ReactElement {
  const sections = Array.isArray(template.schema.sections)
    ? template.schema.sections.map((section) => String(section)).join(", ")
    : "";
  return (
    <article className="rounded-2xl border border-emerald-950/10 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold text-ink">{template.name}</h2>
          <p className="mt-1 text-sm text-slate-600">
            {template.kind.replaceAll("_", " ")} -{" "}
            {template.enabled ? "Enabled" : "Disabled"}
            {template.is_builtin ? " - Built in" : ""}
          </p>
          {sections && (
            <p className="mt-2 text-sm text-slate-700">{sections}</p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="button-secondary"
            disabled={!canPreview}
            onClick={onPreview}
          >
            Preview
          </button>
          <button
            type="button"
            className="button-secondary"
            disabled={template.is_builtin}
            onClick={onToggle}
          >
            {template.enabled ? "Disable" : "Enable"}
          </button>
          <button
            type="button"
            className="button-secondary !text-rose-700"
            disabled={template.is_builtin}
            onClick={onDelete}
          >
            Delete
          </button>
        </div>
      </div>
    </article>
  );
}

function previewSections(
  content: Record<string, unknown>,
): Array<{ heading: string; body: string }> {
  const rawSections = content.sections;
  if (!Array.isArray(rawSections)) return [];
  return rawSections
    .filter(
      (section): section is Record<string, unknown> =>
        typeof section === "object" && section !== null,
    )
    .map((section) => ({
      heading: String(section.heading ?? "Section"),
      body: String(section.body ?? ""),
    }));
}
