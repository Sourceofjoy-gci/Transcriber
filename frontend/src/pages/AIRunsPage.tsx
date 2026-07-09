import { useMemo, useState } from "react";
import type { FormEvent, MouseEvent, ReactElement } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  cancelAIRun,
  createAIRun,
  getAIRun,
  listAIRuns,
  listApiProviders,
  listTranscripts,
  retryAIRun,
} from "../lib/api";
import type { AIRun, AIRunTask, ApiProvider } from "../types";
import {
  EmptyState,
  ErrorBanner,
  LoadingScreen,
  PageHeader,
  Spinner,
  relativeTime,
} from "../components/common";

const TASKS: { value: AIRunTask; label: string; description: string }[] = [
  {
    value: "clean",
    label: "Clean transcript",
    description: "Normalise punctuation and remove obvious artefacts.",
  },
  {
    value: "summary",
    label: "Summary",
    description: "Produce an executive summary of the transcript.",
  },
  {
    value: "minutes",
    label: "Meeting minutes",
    description: "Generate agenda-style minutes with attendees and decisions.",
  },
  {
    value: "action_items",
    label: "Action items",
    description: "Extract assigned actions and owners.",
  },
  {
    value: "topics",
    label: "Topics",
    description: "Identify main topics and themes.",
  },
  {
    value: "entities",
    label: "Entities",
    description: "Extract named entities (people, organisations, places).",
  },
  {
    value: "qa",
    label: "Questions and answers",
    description: "Detect Q&A pairs from the transcript.",
  },
  {
    value: "translate",
    label: "Translate",
    description:
      "Translate the transcript text into the configured target language.",
  },
];

export function AIRunsPage(): ReactElement {
  const queryClient = useQueryClient();
  const transcriptsQuery = useQuery({
    queryKey: ["transcripts"],
    queryFn: () => listTranscripts({ limit: 100 }),
  });
  const providersQuery = useQuery({
    queryKey: ["api-providers"],
    queryFn: listApiProviders,
  });
  const aiRunsQuery = useQuery({
    queryKey: ["ai-runs"],
    queryFn: () => listAIRuns(50),
    refetchInterval: (q) => {
      const runs = q.state.data;
      return runs?.some(
        (run) => run.status === "queued" || run.status === "running",
      )
        ? 1500
        : false;
    },
  });

  const [task, setTask] = useState<AIRunTask>("summary");
  const [transcriptId, setTranscriptId] = useState("");
  const [providerId, setProviderId] = useState<string>("");
  const [egressAcknowledged, setEgressAcknowledged] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const providers = providersQuery.data ?? [];
  const postProcessingProviders = providers.filter(
    (provider) => provider.category === "post_processing",
  );
  const providerById = useMemo(
    () => new Map(providers.map((provider) => [provider.id, provider])),
    [providers],
  );
  const aiRuns = aiRunsQuery.data ?? [];

  const createMutation = useMutation({
    mutationFn: createAIRun,
    onSuccess: (run) => {
      setSelectedRunId(run.id);
      queryClient.invalidateQueries({ queryKey: ["transcripts"] });
      queryClient.invalidateQueries({ queryKey: ["ai-runs"] });
      setFormError(null);
    },
    onError: (e) =>
      setFormError(
        e instanceof ApiError ? e.message : "Failed to queue AI run",
      ),
  });

  const cancelMutation = useMutation({
    mutationFn: (runId: string) => cancelAIRun(runId),
    onSuccess: (run) => {
      queryClient.setQueryData<AIRun[]>(["ai-runs"], (current) =>
        replaceRun(current, run),
      );
      queryClient.setQueryData(["ai-run", run.id], run);
    },
    onError: (e) =>
      setFormError(
        e instanceof ApiError ? e.message : "Failed to cancel AI run",
      ),
  });

  const retryMutation = useMutation({
    mutationFn: (runId: string) => retryAIRun(runId),
    onSuccess: (run) => {
      queryClient.setQueryData<AIRun[]>(["ai-runs"], (current) =>
        replaceRun(current, run),
      );
      queryClient.setQueryData(["ai-run", run.id], run);
      setSelectedRunId(run.id);
    },
    onError: (e) =>
      setFormError(
        e instanceof ApiError ? e.message : "Failed to retry AI run",
      ),
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (!transcriptId) {
      setFormError("Transcript is required");
      return;
    }
    if (providerId && !egressAcknowledged) {
      setFormError("External AI runs require egress acknowledgement");
      return;
    }
    setFormError(null);
    createMutation.mutate({
      transcript_id: transcriptId,
      task,
      execution_target_kind: providerId ? "api_provider" : "automatic",
      execution_target_id: providerId || null,
      egress_acknowledged: Boolean(providerId && egressAcknowledged),
    });
  }

  return (
    <section className="space-y-6">
      <PageHeader
        eyebrow="Intelligence"
        title="AI Post-Processing"
        subtitle="Run cleanup, summarisation, extraction, and translation tasks over completed transcripts."
      />

      {formError && (
        <ErrorBanner message={formError} onRetry={() => setFormError(null)} />
      )}

      <article className="rounded-2xl border border-emerald-950/10 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-bold">Queue a new AI run</h2>
        <form
          className="mt-4 grid gap-4 sm:grid-cols-2"
          onSubmit={handleSubmit}
        >
          <label className="field-label">
            Task
            <select
              className="field-input"
              value={task}
              onChange={(e) => setTask(e.target.value as AIRunTask)}
            >
              {TASKS.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
            <span className="text-xs text-slate-500">
              {TASKS.find((t) => t.value === task)?.description}
            </span>
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
              {transcriptsQuery.data?.map((t) => (
                <option key={t.id} value={t.id}>
                  Transcript {t.id.slice(0, 8)} ·{" "}
                  {t.detected_language ?? "auto"}
                </option>
              ))}
            </select>
          </label>
          <label className="field-label sm:col-span-2">
            Provider (optional — leave empty for automatic)
            <select
              className="field-input"
              value={providerId}
              onChange={(e) => {
                setProviderId(e.target.value);
                if (!e.target.value) setEgressAcknowledged(false);
              }}
            >
              <option value="">Automatic / local</option>
              {postProcessingProviders.map((p) => (
                <option key={p.id} value={p.id} disabled={!p.enabled}>
                  {p.name} {!p.enabled && "(disabled)"}
                </option>
              ))}
            </select>
          </label>
          {providerId && (
            <label className="sm:col-span-2 flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
              <input
                type="checkbox"
                className="mt-1"
                checked={egressAcknowledged}
                onChange={(event) =>
                  setEgressAcknowledged(event.target.checked)
                }
                required
              />
              <span>
                I confirm this AI run may send transcript text to the selected
                external provider.
              </span>
            </label>
          )}
          <div className="sm:col-span-2 flex gap-2">
            <button
              type="submit"
              className="button-primary"
              disabled={createMutation.isPending}
            >
              {createMutation.isPending ? <Spinner /> : "Queue AI run"}
            </button>
          </div>
        </form>
      </article>

      {aiRuns.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-lg font-bold">Run history</h2>
          {aiRuns.map((run) => (
            <AIRunCard
              key={run.id}
              run={run}
              provider={
                run.execution_target_id
                  ? providerById.get(run.execution_target_id)
                  : undefined
              }
              onSelect={() => setSelectedRunId(run.id)}
              onCancel={() => cancelMutation.mutate(run.id)}
              onRetry={() => retryMutation.mutate(run.id)}
            />
          ))}
        </div>
      )}

      {aiRunsQuery.isLoading && (
        <LoadingScreen message="Loading AI run historyâ€¦" />
      )}

      {!transcriptsQuery.data?.length && !transcriptsQuery.isLoading && (
        <EmptyState
          title="No transcripts available"
          hint="Transcribe a recording first, then queue AI tasks against its transcript."
        />
      )}

      {selectedRunId && (
        <AIRunViewer
          runId={selectedRunId}
          onClose={() => setSelectedRunId(null)}
        />
      )}
    </section>
  );
}

function AIRunCard({
  run,
  provider,
  onSelect,
  onCancel,
  onRetry,
}: {
  run: AIRun;
  provider?: ApiProvider;
  onSelect: () => void;
  onCancel: () => void;
  onRetry: () => void;
}): ReactElement {
  const canCancel = run.status === "queued" || run.status === "running";
  const canRetry = run.status === "failed" || run.status === "cancelled";

  function handleAction(
    event: MouseEvent<HTMLButtonElement>,
    action: () => void,
  ): void {
    event.stopPropagation();
    action();
  }

  return (
    <article
      role="button"
      tabIndex={0}
      className="w-full rounded-2xl border border-emerald-950/10 bg-white p-4 text-left shadow-sm transition hover:border-emerald-700/30"
      onClick={onSelect}
      onKeyDown={(event) => {
        if (
          event.target === event.currentTarget &&
          (event.key === "Enter" || event.key === " ")
        ) {
          onSelect();
        }
      }}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-semibold capitalize">
            {run.task.replaceAll("_", " ")}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            {formatTarget(run, provider)} Â· created{" "}
            {relativeTime(run.created_at)}
          </p>
        </div>
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-semibold ${statusClass(run.status)}`}
        >
          {run.status}
        </span>
      </div>
      <div className="mt-3">
        <div className="h-2 overflow-hidden rounded-full bg-slate-100">
          <div
            className="h-full rounded-full bg-fern transition-all"
            style={{
              width: `${Math.max(0, Math.min(100, run.progress_percent))}%`,
            }}
          />
        </div>
        <div className="mt-1 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-600">
          <span>{run.progress_percent}%</span>
          <span>
            {run.progress_message ?? run.error_message ?? "No progress message"}
          </span>
        </div>
      </div>
      {run.error_message && (
        <p className="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">
          {run.error_message}
        </p>
      )}
      {(canCancel || canRetry) && (
        <div className="mt-4 flex flex-wrap gap-2">
          {canCancel && (
            <button
              type="button"
              className="button-secondary"
              onClick={(event) => handleAction(event, onCancel)}
            >
              Cancel
            </button>
          )}
          {canRetry && (
            <button
              type="button"
              className="button-secondary"
              onClick={(event) => handleAction(event, onRetry)}
            >
              Retry
            </button>
          )}
        </div>
      )}
    </article>
  );
}

function AIRunViewer({
  runId,
  onClose,
}: {
  runId: string;
  onClose: () => void;
}): ReactElement {
  const query = useQuery({
    queryKey: ["ai-run", runId],
    queryFn: () => getAIRun(runId),
    refetchInterval: (q) => {
      const status = q.state.data?.status;
      return status === "completed" ||
        status === "failed" ||
        status === "cancelled"
        ? false
        : 1500;
    },
  });
  const live = query.data;
  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-40 grid place-items-center bg-slate-900/50 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white p-6 shadow-xl">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-xl font-bold">
              AI run · {live?.task.replaceAll("_", " ") ?? "loading…"}
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              Status:{" "}
              <span className="font-semibold">
                {live?.status ?? "loading…"}
              </span>
              {live?.created_at && (
                <> · created {relativeTime(live.created_at)}</>
              )}
            </p>
          </div>
          <button type="button" className="button-secondary" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="mt-5">
          {query.isLoading && <LoadingScreen message="Loading run…" />}
          {live?.status === "failed" && (
            <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">
              {live.error_message ?? "Run failed."}
            </p>
          )}
          {live?.status === "cancelled" && (
            <p className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700">
              Run cancelled.
            </p>
          )}
          {(live?.status === "queued" || live?.status === "running") && (
            <p className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700">
              <Spinner /> Working — this dialog will update automatically.
            </p>
          )}
          {live?.status === "completed" && (
            <pre className="overflow-x-auto rounded-lg bg-slate-50 p-3 text-xs text-slate-700">
              {JSON.stringify(live.result, null, 2)}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}

function replaceRun(current: AIRun[] | undefined, replacement: AIRun): AIRun[] {
  if (!current) return [replacement];
  return current.map((run) => (run.id === replacement.id ? replacement : run));
}

function formatTarget(run: AIRun, provider?: ApiProvider): string {
  if (run.execution_target_kind === "api_provider") {
    return provider?.name ?? "API provider";
  }
  if (run.execution_target_kind === "local_model") {
    return "Local model";
  }
  return "Automatic / local";
}

function statusClass(status: AIRun["status"]): string {
  if (status === "completed") return "bg-emerald-100 text-emerald-800";
  if (status === "failed") return "bg-rose-100 text-rose-700";
  if (status === "cancelled") return "bg-slate-100 text-slate-700";
  if (status === "running") return "bg-blue-100 text-blue-800";
  return "bg-amber-100 text-amber-800";
}
