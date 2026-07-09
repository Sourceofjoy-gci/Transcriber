import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactElement } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  annotateTranscriptSegment,
  assignTranscriptSegmentSpeaker,
  batchEditTranscriptSegments,
  createAssetDownloadUrl,
  createExport,
  createAIRun,
  createTranscriptSpeaker,
  editTranscriptSegment,
  exportDownloadUrl,
  getTranscript,
  listAssetDerivatives,
  listTranscriptSpeakers,
  listTranscriptVersions,
  mergeTranscriptSegments,
  redoTranscriptOperation,
  replaceTranscriptText,
  restoreTranscriptVersion,
  searchTranscript,
  splitTranscriptSegment,
  undoTranscriptOperation,
  updateTranscriptSpeaker,
} from "../lib/api";
import type {
  ExportFormat,
  Speaker,
  TranscriptDetail,
  TranscriptVersion,
} from "../types";
import { ALL_EXPORT_FORMATS } from "../types";
import {
  ConfirmDialog,
  EmptyState,
  ErrorBanner,
  LoadingScreen,
  formatBytes,
  formatTimestamp,
} from "../components/common";

export function TranscriptViewerPage(): ReactElement {
  const { transcriptId } = useParams<{ transcriptId: string }>();
  const queryClient = useQueryClient();
  const playerRef = useRef<HTMLAudioElement>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [replaceText, setReplaceText] = useState("");
  const [exportMessage, setExportMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [showVersions, setShowVersions] = useState(false);
  const [showSpeakers, setShowSpeakers] = useState(false);
  const [showAiRuns, setShowAiRuns] = useState(false);
  const [newSpeakerLabel, setNewSpeakerLabel] = useState("");
  const [newSpeakerName, setNewSpeakerName] = useState("");
  const [selectedExportSegmentIds, setSelectedExportSegmentIds] = useState<
    string[]
  >([]);

  const transcriptQuery = useQuery({
    queryKey: ["transcript", transcriptId],
    queryFn: () => getTranscript(transcriptId!),
    enabled: Boolean(transcriptId),
  });
  const versionsQuery = useQuery({
    queryKey: ["transcript-versions", transcriptId],
    queryFn: () => listTranscriptVersions(transcriptId!),
    enabled: Boolean(transcriptId) && showVersions,
  });
  const transcriptHasAssignedSpeakers =
    transcriptQuery.data?.segments.some((segment) =>
      Boolean(segment.speaker_id),
    ) ?? false;
  const speakersQuery = useQuery({
    queryKey: ["transcript-speakers", transcriptId],
    queryFn: () => listTranscriptSpeakers(transcriptId!),
    enabled:
      Boolean(transcriptId) && (showSpeakers || transcriptHasAssignedSpeakers),
  });
  const searchQueryResult = useQuery({
    queryKey: ["transcript-search", transcriptId, searchQuery],
    queryFn: () => searchTranscript(transcriptId!, searchQuery),
    enabled: Boolean(transcriptId) && searchQuery.length >= 2,
  });
  const assetDownloadQuery = useQuery({
    queryKey: ["asset-download-url", transcriptQuery.data?.asset_id],
    queryFn: () => createAssetDownloadUrl(transcriptQuery.data!.asset_id),
    enabled: Boolean(transcriptQuery.data?.asset_id),
    staleTime: 4 * 60 * 1000,
  });
  const derivativesQuery = useQuery({
    queryKey: ["asset-derivatives", transcriptQuery.data?.asset_id],
    queryFn: () => listAssetDerivatives(transcriptQuery.data!.asset_id),
    enabled: Boolean(transcriptQuery.data?.asset_id),
    refetchInterval: 10000,
  });

  const exportMutation = useMutation({
    mutationFn: (format: ExportFormat) =>
      createExport({
        source_type: "transcript",
        transcript_id: transcriptId!,
        format,
        segment_ids: selectedExportSegmentIds,
        options: {},
      }),
    onSuccess: (exportRecord) => {
      setExportMessage(
        `${exportRecord.format.toUpperCase()} export ${exportRecord.status}. It will be ready shortly.`,
      );
      queryClient.invalidateQueries({ queryKey: ["transcript", transcriptId] });
    },
    onError: (e) =>
      setExportMessage(e instanceof ApiError ? e.message : "Export failed"),
  });

  const editMutation = useMutation({
    mutationFn: ({ segmentId, text }: { segmentId: string; text: string }) =>
      editTranscriptSegment(transcriptId!, segmentId, {
        base_version_id: transcriptQuery.data?.active_version?.id,
        text,
        change_summary: "Inline edit",
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["transcript", transcriptId], updated);
      setEditingId(null);
    },
    onError: (e) =>
      setActionError(e instanceof ApiError ? e.message : "Edit failed"),
  });

  const splitMutation = useMutation({
    mutationFn: ({
      segmentId,
      splitAtMs,
    }: {
      segmentId: string;
      splitAtMs: number;
    }) =>
      splitTranscriptSegment(
        transcriptId!,
        segmentId,
        splitAtMs,
        transcriptQuery.data?.active_version?.id,
      ),
    onSuccess: (updated) => {
      queryClient.setQueryData(["transcript", transcriptId], updated);
    },
    onError: (e) =>
      setActionError(e instanceof ApiError ? e.message : "Split failed"),
  });

  const mergeMutation = useMutation({
    mutationFn: ({
      firstId,
      secondId,
    }: {
      firstId: string;
      secondId: string;
    }) =>
      mergeTranscriptSegments(
        transcriptId!,
        firstId,
        secondId,
        transcriptQuery.data?.active_version?.id,
      ),
    onSuccess: (updated) => {
      queryClient.setQueryData(["transcript", transcriptId], updated);
    },
    onError: (e) =>
      setActionError(e instanceof ApiError ? e.message : "Merge failed"),
  });

  const annotateMutation = useMutation({
    mutationFn: ({
      segmentId,
      note,
      is_unclear,
    }: {
      segmentId: string;
      note?: string;
      is_unclear?: boolean;
    }) =>
      annotateTranscriptSegment(transcriptId!, segmentId, {
        base_version_id: transcriptQuery.data?.active_version?.id,
        note,
        is_unclear,
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["transcript", transcriptId], updated);
    },
    onError: (e) =>
      setActionError(e instanceof ApiError ? e.message : "Annotation failed"),
  });

  const restoreVersionMutation = useMutation({
    mutationFn: (versionId: string) =>
      restoreTranscriptVersion(
        transcriptId!,
        versionId,
        transcriptQuery.data?.active_version?.id,
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["transcript", transcriptId] });
      queryClient.invalidateQueries({
        queryKey: ["transcript-versions", transcriptId],
      });
    },
    onError: (e) =>
      setActionError(e instanceof ApiError ? e.message : "Restore failed"),
  });

  const assignSpeakerMutation = useMutation({
    mutationFn: ({
      segmentId,
      speakerId,
    }: {
      segmentId: string;
      speakerId: string | null;
    }) =>
      assignTranscriptSegmentSpeaker(transcriptId!, segmentId, {
        base_version_id: transcriptQuery.data?.active_version?.id,
        speaker_id: speakerId,
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["transcript", transcriptId], updated);
      queryClient.invalidateQueries({
        queryKey: ["transcript-versions", transcriptId],
      });
    },
    onError: (e) =>
      setActionError(
        e instanceof ApiError ? e.message : "Speaker assignment failed",
      ),
  });

  const replaceMutation = useMutation({
    mutationFn: () =>
      replaceTranscriptText(transcriptId!, {
        base_version_id: transcriptQuery.data?.active_version?.id,
        query: searchQuery,
        replacement: replaceText,
        replace_all: true,
      }),
    onSuccess: (result) => {
      queryClient.setQueryData(["transcript", transcriptId], result.transcript);
      queryClient.invalidateQueries({
        queryKey: ["transcript-versions", transcriptId],
      });
      setExportMessage(
        `${result.replacement_count} replacement${result.replacement_count === 1 ? "" : "s"} applied.`,
      );
    },
    onError: (e) =>
      setActionError(e instanceof ApiError ? e.message : "Replace failed"),
  });

  const undoMutation = useMutation({
    mutationFn: () =>
      undoTranscriptOperation(transcriptId!, {
        base_version_id: transcriptQuery.data?.active_version?.id,
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["transcript", transcriptId], updated);
      queryClient.invalidateQueries({
        queryKey: ["transcript-versions", transcriptId],
      });
    },
    onError: (e) =>
      setActionError(e instanceof ApiError ? e.message : "Undo failed"),
  });

  const redoMutation = useMutation({
    mutationFn: () =>
      redoTranscriptOperation(transcriptId!, {
        base_version_id: transcriptQuery.data?.active_version?.id,
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["transcript", transcriptId], updated);
      queryClient.invalidateQueries({
        queryKey: ["transcript-versions", transcriptId],
      });
    },
    onError: (e) =>
      setActionError(e instanceof ApiError ? e.message : "Redo failed"),
  });

  const createSpeakerMutation = useMutation({
    mutationFn: () =>
      createTranscriptSpeaker(transcriptId!, {
        label: newSpeakerLabel.trim(),
        display_name: newSpeakerName.trim() || undefined,
      }),
    onSuccess: () => {
      setNewSpeakerLabel("");
      setNewSpeakerName("");
      speakersQuery.refetch();
    },
    onError: (e) =>
      setActionError(
        e instanceof ApiError ? e.message : "Speaker creation failed",
      ),
  });

  const aiMutation = useMutation({
    mutationFn: (
      task: "summary" | "clean" | "minutes" | "action_items" | "topics",
    ) => createAIRun({ transcript_id: transcriptId!, task }),
    onSuccess: () => {
      setShowAiRuns(false);
      queryClient.invalidateQueries({ queryKey: ["ai-runs"] });
    },
    onError: (e) =>
      setActionError(e instanceof ApiError ? e.message : "AI run failed"),
  });

  // Keep audio playback position synced to currently visible segment (best-effort).
  const [activeSegmentIndex, setActiveSegmentIndex] = useState(0);
  useEffect(() => {
    const audio = playerRef.current;
    if (!audio) return;
    const handleTimeUpdate = () => {
      const t = audio.currentTime * 1000;
      const idx =
        transcriptQuery.data?.segments.findIndex(
          (s) => s.start_ms <= t && t <= s.end_ms,
        ) ?? -1;
      if (idx >= 0) setActiveSegmentIndex(idx);
    };
    audio.addEventListener("timeupdate", handleTimeUpdate);
    return () => audio.removeEventListener("timeupdate", handleTimeUpdate);
  }, [transcriptQuery.data?.segments]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const tagName = target?.tagName;
      const isFormField =
        tagName === "INPUT" || tagName === "TEXTAREA" || tagName === "SELECT";
      const segments = transcriptQuery.data?.segments ?? [];
      const activeSegment = segments[activeSegmentIndex];
      const nextSegment = segments[activeSegmentIndex + 1];
      if (
        (event.ctrlKey || event.metaKey) &&
        event.key.toLowerCase() === "z" &&
        !event.shiftKey
      ) {
        event.preventDefault();
        undoMutation.mutate();
        return;
      }
      if (
        ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "y") ||
        ((event.ctrlKey || event.metaKey) &&
          event.shiftKey &&
          event.key.toLowerCase() === "z")
      ) {
        event.preventDefault();
        redoMutation.mutate();
        return;
      }
      if (
        (event.ctrlKey || event.metaKey) &&
        event.shiftKey &&
        event.key.toLowerCase() === "s" &&
        activeSegment
      ) {
        event.preventDefault();
        splitMutation.mutate({
          segmentId: activeSegment.id,
          splitAtMs: Math.floor(
            (activeSegment.start_ms + activeSegment.end_ms) / 2,
          ),
        });
        return;
      }
      if (
        (event.ctrlKey || event.metaKey) &&
        event.key.toLowerCase() === "m" &&
        activeSegment &&
        nextSegment
      ) {
        event.preventDefault();
        mergeMutation.mutate({
          firstId: activeSegment.id,
          secondId: nextSegment.id,
        });
        return;
      }
      if (
        (event.ctrlKey || event.metaKey) &&
        event.shiftKey &&
        event.key.toLowerCase() === "u" &&
        activeSegment
      ) {
        event.preventDefault();
        annotateMutation.mutate({
          segmentId: activeSegment.id,
          is_unclear: !activeSegment.is_unclear,
        });
        return;
      }
      if (
        event.altKey &&
        /^[1-9]$/.test(event.key) &&
        activeSegment &&
        speakersQuery.data
      ) {
        const speaker = speakersQuery.data[Number(event.key) - 1];
        if (speaker) {
          event.preventDefault();
          assignSpeakerMutation.mutate({
            segmentId: activeSegment.id,
            speakerId: speaker.id,
          });
          return;
        }
      }
      if (isFormField) return;
      if (event.key === " ") {
        event.preventDefault();
        const audio = playerRef.current;
        if (audio?.paused) {
          void audio.play();
        } else {
          audio?.pause();
        }
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        setActiveSegmentIndex((index) =>
          Math.min((transcriptQuery.data?.segments.length ?? 1) - 1, index + 1),
        );
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setActiveSegmentIndex((index) => Math.max(0, index - 1));
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [
    activeSegmentIndex,
    annotateMutation,
    assignSpeakerMutation,
    mergeMutation,
    redoMutation,
    speakersQuery.data,
    splitMutation,
    transcriptQuery.data?.segments,
    undoMutation,
  ]);

  const transcript = transcriptQuery.data;

  useEffect(() => {
    const availableIds = new Set(
      transcript?.segments.map((segment) => segment.id) ?? [],
    );
    setSelectedExportSegmentIds((ids) =>
      ids.filter((id) => availableIds.has(id)),
    );
  }, [transcript?.segments]);

  const speakerBySegmentId = useMemo(() => {
    if (!transcript || !speakersQuery.data) return new Map<string, Speaker>();
    const map = new Map<string, Speaker>();
    transcript.segments.forEach((segment) => {
      if (segment.speaker_id) {
        const speaker = speakersQuery.data.find(
          (s) => s.id === segment.speaker_id,
        );
        if (speaker) map.set(segment.id, speaker);
      }
    });
    return map;
  }, [speakersQuery.data, transcript]);

  if (transcriptQuery.isLoading)
    return <LoadingScreen message="Loading transcript…" />;
  if (!transcript) return <ErrorBanner message="Transcript not found." />;

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <Link
            className="text-sm font-semibold text-fern hover:underline"
            to="/transcripts"
          >
            ← All transcripts
          </Link>
          <p className="eyebrow mt-4">
            Version {transcript.active_version?.version_number ?? "—"}
          </p>
          <h1 className="page-title">Transcript review</h1>
          <p className="page-subtitle">
            {transcript.segments.length} timestamped segments ·{" "}
            {transcript.source_provider.replaceAll("_", " ")}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="button-secondary"
            onClick={() => undoMutation.mutate()}
          >
            Undo
          </button>
          <button
            type="button"
            className="button-secondary"
            onClick={() => redoMutation.mutate()}
          >
            Redo
          </button>
          <button
            type="button"
            className="button-secondary"
            onClick={() => setShowVersions((v) => !v)}
          >
            {showVersions ? "Hide history" : "Version history"}
          </button>
          <button
            type="button"
            className="button-secondary"
            onClick={() => setShowSpeakers((v) => !v)}
          >
            {showSpeakers ? "Hide speakers" : "Speakers"}
          </button>
          <button
            type="button"
            className="button-secondary"
            onClick={() => setShowAiRuns((v) => !v)}
          >
            AI tasks
          </button>
        </div>
      </div>

      {actionError && (
        <ErrorBanner
          message={actionError}
          onRetry={() => setActionError(null)}
        />
      )}

      <article className="rounded-2xl border border-emerald-950/10 bg-white p-4 shadow-sm">
        <label className="field-label">
          Search within transcript
          <input
            className="field-input"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onInput={(e) => setSearchQuery(e.currentTarget.value)}
            placeholder="Type to search for a word or phrase"
          />
        </label>
        <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_auto]">
          <label className="field-label">
            Replace with
            <input
              className="field-input"
              value={replaceText}
              onChange={(e) => setReplaceText(e.target.value)}
              onInput={(e) => setReplaceText(e.currentTarget.value)}
              placeholder="Replacement text"
            />
          </label>
          <button
            type="button"
            className="button-secondary self-end"
            disabled={
              replaceMutation.isPending || searchQuery.trim().length === 0
            }
            onClick={() => replaceMutation.mutate()}
          >
            Replace all
          </button>
        </div>
        {searchQueryResult.data && searchQuery.length >= 2 && (
          <div className="mt-3 space-y-2 text-sm">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              {searchQueryResult.data.hits.length} match
              {searchQueryResult.data.hits.length === 1 ? "" : "es"}
            </p>
            {searchQueryResult.data.hits.slice(0, 8).map((hit) => (
              <button
                key={hit.segment_id}
                type="button"
                className="block w-full rounded-lg bg-amber-50 px-3 py-2 text-left text-slate-800 transition hover:bg-amber-100"
                onClick={() => {
                  if (playerRef.current)
                    playerRef.current.currentTime = hit.start_ms / 1000;
                  const el = document.getElementById(
                    `segment-${hit.segment_id}`,
                  );
                  el?.scrollIntoView({ behavior: "smooth", block: "center" });
                }}
              >
                <span className="font-mono text-xs font-semibold text-amber-800">
                  {formatTimestamp(hit.start_ms)}
                </span>{" "}
                …{hit.snippet}…
              </button>
            ))}
          </div>
        )}
      </article>

      <div className="overflow-hidden rounded-2xl border border-emerald-950/10 bg-white shadow-sm">
        <audio
          ref={playerRef}
          className="w-full border-b border-slate-100 p-4"
          controls
          preload="metadata"
          src={assetDownloadQuery.data?.url}
        />
        {assetDownloadQuery.isError && (
          <p className="border-b border-slate-100 px-4 py-2 text-sm text-rose-700">
            Media playback URL is unavailable.
          </p>
        )}
        {derivativesQuery.data && derivativesQuery.data.items.length > 0 && (
          <div className="flex flex-wrap gap-2 border-b border-slate-100 px-4 py-3 text-xs">
            {derivativesQuery.data.items.map((derivative) => (
              <span
                key={derivative.id}
                className="rounded-full bg-slate-100 px-2 py-1 font-semibold text-slate-700"
              >
                {derivative.kind.replaceAll("_", " ")} {derivative.status}
                {derivative.byte_size > 0
                  ? ` - ${formatBytes(derivative.byte_size)}`
                  : ""}
              </span>
            ))}
          </div>
        )}
        {transcript.segments.map((segment, idx) => {
          const speaker = speakerBySegmentId.get(segment.id);
          const speakerLabel = speaker
            ? (speaker.display_name ?? speaker.label)
            : segment.speaker_label;
          const isActive = idx === activeSegmentIndex;
          return (
            <article
              key={segment.id}
              id={`segment-${segment.id}`}
              className={`grid gap-3 border-b border-slate-100 p-5 last:border-b-0 sm:grid-cols-[8rem_1fr_auto] ${
                isActive ? "bg-emerald-50/40" : ""
              }`}
            >
              <div className="flex items-center gap-2">
                <input
                  aria-label={`Select segment ${segment.sequence} for export`}
                  type="checkbox"
                  className="h-4 w-4 rounded border-slate-300 text-fern focus:ring-emerald-100"
                  checked={selectedExportSegmentIds.includes(segment.id)}
                  onChange={(event) => {
                    const checked = event.target.checked;
                    setSelectedExportSegmentIds((ids) =>
                      checked
                        ? [...ids, segment.id]
                        : ids.filter((id) => id !== segment.id),
                    );
                  }}
                />
                <button
                  className="font-mono text-left text-sm font-semibold text-fern hover:underline"
                  onClick={() => {
                    if (playerRef.current)
                      playerRef.current.currentTime = segment.start_ms / 1000;
                  }}
                >
                  {formatTimestamp(segment.start_ms)}
                </button>
              </div>
              {speakerLabel && (
                <span
                  className="self-start rounded-full px-2 py-0.5 text-xs font-semibold text-white"
                  style={{ backgroundColor: speaker?.color ?? "#475569" }}
                >
                  {speakerLabel}
                </span>
              )}
              {editingId === segment.id ? (
                <div className="sm:col-span-3 space-y-2">
                  <textarea
                    className="field-input min-h-24 w-full"
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    aria-label="Edit segment text"
                  />
                  <div className="flex gap-2">
                    <button
                      type="button"
                      className="button-primary"
                      disabled={editMutation.isPending}
                      onClick={() =>
                        editMutation.mutate({
                          segmentId: segment.id,
                          text: draft,
                        })
                      }
                    >
                      Save version
                    </button>
                    <button
                      type="button"
                      className="button-secondary"
                      onClick={() => setEditingId(null)}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div className="sm:col-span-2">
                  {showSpeakers && speakersQuery.data && (
                    <label className="mb-2 block max-w-xs text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Speaker
                      <select
                        aria-label="Assign speaker"
                        className="field-input mt-1 !py-1 !text-sm"
                        value={segment.speaker_id ?? ""}
                        onChange={(event) =>
                          assignSpeakerMutation.mutate({
                            segmentId: segment.id,
                            speakerId: event.target.value || null,
                          })
                        }
                      >
                        <option value="">Unassigned</option>
                        {speakersQuery.data.map((availableSpeaker) => (
                          <option
                            key={availableSpeaker.id}
                            value={availableSpeaker.id}
                          >
                            {availableSpeaker.display_name ??
                              availableSpeaker.label}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                  <button
                    type="button"
                    className="text-left leading-7 text-slate-800 hover:text-moss"
                    onClick={() => {
                      setEditingId(segment.id);
                      setDraft(segment.text);
                    }}
                  >
                    {segment.text}
                    {segment.is_unclear && (
                      <span className="ml-2 rounded bg-amber-200 px-1.5 py-0.5 text-xs">
                        unclear
                      </span>
                    )}
                  </button>
                  {segment.notes && (
                    <p className="mt-2 whitespace-pre-wrap rounded bg-slate-50 px-2 py-1 text-xs text-slate-600">
                      {segment.notes}
                    </p>
                  )}
                </div>
              )}
            </article>
          );
        })}
        {!transcript.segments.length && (
          <EmptyState
            title="This transcript contains no segments."
            hint="The job may still be running."
          />
        )}
      </div>

      {exportMessage && (
        <p className="rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          {exportMessage}
        </p>
      )}

      <ExportPanel
        onExport={(format: ExportFormat) => {
          setExportMessage(null);
          exportMutation.mutate(format);
        }}
        isPending={exportMutation.isPending}
        selectedCount={selectedExportSegmentIds.length}
        onClearSelection={() => setSelectedExportSegmentIds([])}
      />

      {showVersions && versionsQuery.data && (
        <VersionHistory
          versions={versionsQuery.data}
          activeVersionId={transcript.active_version?.id ?? null}
          onRestore={(id) => restoreVersionMutation.mutate(id)}
        />
      )}

      {showSpeakers && speakersQuery.data && (
        <SpeakerPanel
          speakers={speakersQuery.data}
          newSpeakerLabel={newSpeakerLabel}
          newSpeakerName={newSpeakerName}
          onNewSpeakerLabelChange={setNewSpeakerLabel}
          onNewSpeakerNameChange={setNewSpeakerName}
          onCreateSpeaker={() => createSpeakerMutation.mutate()}
          isCreatingSpeaker={createSpeakerMutation.isPending}
          onUpdate={(speakerId, patch) =>
            updateTranscriptSpeaker(transcriptId!, speakerId, patch).then(() =>
              speakersQuery.refetch(),
            )
          }
        />
      )}

      {showAiRuns && (
        <article className="rounded-2xl border border-emerald-950/10 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-bold">AI tasks</h2>
          <p className="mt-1 text-sm text-slate-600">
            Queue a post-processing task against this transcript. View results
            in the AI Runs page.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {(
              ["summary", "clean", "minutes", "action_items", "topics"] as const
            ).map((task) => (
              <button
                key={task}
                type="button"
                className="button-secondary"
                disabled={aiMutation.isPending}
                onClick={() => aiMutation.mutate(task)}
              >
                {task.replaceAll("_", " ")}
              </button>
            ))}
          </div>
        </article>
      )}

      <ConfirmDialog
        open={false}
        title=""
        message=""
        onConfirm={() => undefined}
        onCancel={() => undefined}
      />
    </section>
  );
}

function ExportPanel({
  onExport,
  isPending,
  selectedCount,
  onClearSelection,
}: {
  onExport: (format: ExportFormat) => void;
  isPending: boolean;
  selectedCount: number;
  onClearSelection: () => void;
}): ReactElement {
  return (
    <article className="rounded-2xl border border-emerald-950/10 bg-white p-5 shadow-sm">
      <h2 className="text-lg font-bold">Export transcript</h2>
      <p className="mt-1 text-sm text-slate-600">
        Choose a format. The export will be available from the queue once
        generated.
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-slate-600">
        <span>
          {selectedCount > 0
            ? `${selectedCount} selected segment${selectedCount === 1 ? "" : "s"}`
            : "Full transcript"}
        </span>
        {selectedCount > 0 && (
          <button
            type="button"
            className="button-secondary !py-1 text-xs"
            onClick={onClearSelection}
          >
            Clear selection
          </button>
        )}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {ALL_EXPORT_FORMATS.map((format) => (
          <button
            key={format}
            type="button"
            className="button-secondary uppercase"
            disabled={isPending}
            onClick={() => onExport(format)}
          >
            {format.toUpperCase()}
          </button>
        ))}
      </div>
      <p className="mt-3 text-xs text-slate-500">
        Visit the{" "}
        <Link className="font-semibold text-fern hover:underline" to="/exports">
          exports page
        </Link>{" "}
        to download completed files.
      </p>
    </article>
  );
}

function VersionHistory({
  versions,
  activeVersionId,
  onRestore,
}: {
  versions: TranscriptVersion[];
  activeVersionId: string | null;
  onRestore: (id: string) => void;
}): ReactElement {
  return (
    <article className="rounded-2xl border border-emerald-950/10 bg-white p-5 shadow-sm">
      <h2 className="text-lg font-bold">Version history</h2>
      <ul className="mt-3 space-y-2">
        {versions.map((version) => (
          <li
            key={version.id}
            className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-50 px-3 py-2"
          >
            <div>
              <p className="font-semibold">v{version.version_number}</p>
              <p className="text-xs text-slate-500">
                {version.source.replaceAll("_", " ")} ·{" "}
                {version.change_summary ?? "—"}
              </p>
            </div>
            <div className="flex gap-2">
              {activeVersionId === version.id ? (
                <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-800">
                  Active
                </span>
              ) : (
                <button
                  type="button"
                  className="button-secondary"
                  onClick={() => onRestore(version.id)}
                >
                  Restore
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </article>
  );
}

function SpeakerPanel({
  speakers,
  newSpeakerLabel,
  newSpeakerName,
  onNewSpeakerLabelChange,
  onNewSpeakerNameChange,
  onCreateSpeaker,
  isCreatingSpeaker,
  onUpdate,
}: {
  speakers: Speaker[];
  newSpeakerLabel: string;
  newSpeakerName: string;
  onNewSpeakerLabelChange: (value: string) => void;
  onNewSpeakerNameChange: (value: string) => void;
  onCreateSpeaker: () => void;
  isCreatingSpeaker: boolean;
  onUpdate: (
    id: string,
    patch: { display_name?: string; color?: string },
  ) => void;
}): ReactElement {
  return (
    <article className="rounded-2xl border border-emerald-950/10 bg-white p-5 shadow-sm">
      <h2 className="text-lg font-bold">Speakers</h2>
      <div className="mt-3 grid gap-3 sm:grid-cols-[8rem_1fr_auto]">
        <input
          className="field-input"
          value={newSpeakerLabel}
          onChange={(event) => onNewSpeakerLabelChange(event.target.value)}
          placeholder="Label"
        />
        <input
          className="field-input"
          value={newSpeakerName}
          onChange={(event) => onNewSpeakerNameChange(event.target.value)}
          placeholder="Display name"
        />
        <button
          type="button"
          className="button-secondary"
          disabled={isCreatingSpeaker || !newSpeakerLabel.trim()}
          onClick={onCreateSpeaker}
        >
          Add speaker
        </button>
      </div>
      {speakers.length === 0 ? (
        <p className="mt-2 text-sm text-slate-500">
          No speakers assigned to this transcript yet.
        </p>
      ) : (
        <ul className="mt-3 space-y-2">
          {speakers.map((speaker) => (
            <li
              key={speaker.id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-50 px-3 py-2"
            >
              <div className="flex items-center gap-2">
                <span
                  className="inline-block h-3 w-3 rounded-full"
                  style={{ backgroundColor: speaker.color ?? "#475569" }}
                />
                <span className="font-semibold">{speaker.label}</span>
                {speaker.display_name && (
                  <span className="text-sm text-slate-500">
                    ({speaker.display_name})
                  </span>
                )}
              </div>
              <div className="flex gap-2">
                <input
                  className="field-input !py-1 !text-xs"
                  defaultValue={speaker.display_name ?? ""}
                  placeholder="Display name"
                  onBlur={(e) =>
                    onUpdate(speaker.id, { display_name: e.target.value })
                  }
                />
                <input
                  type="color"
                  defaultValue={speaker.color ?? "#475569"}
                  className="h-8 w-10 rounded border border-slate-300"
                  onBlur={(e) =>
                    onUpdate(speaker.id, { color: e.target.value })
                  }
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}

// Re-export helper for download URLs (used by exports listing)
export { exportDownloadUrl };
