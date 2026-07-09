import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { TranscriptViewerPage } from "./TranscriptViewerPage";
import {
  annotateTranscriptSegment,
  assignTranscriptSegmentSpeaker,
  createAssetDownloadUrl,
  createExport,
  getTranscript,
  listAssetDerivatives,
  listTranscriptSpeakers,
  mergeTranscriptSegments,
  redoTranscriptOperation,
  replaceTranscriptText,
  searchTranscript,
  splitTranscriptSegment,
  undoTranscriptOperation,
} from "../lib/api";

vi.mock("../lib/api", () => ({
  ApiError: class ApiError extends Error {},
  annotateTranscriptSegment: vi.fn(),
  assignTranscriptSegmentSpeaker: vi.fn(),
  createAIRun: vi.fn(),
  createExport: vi.fn(),
  createTranscriptSpeaker: vi.fn(),
  editTranscriptSegment: vi.fn(),
  exportDownloadUrl: vi.fn(),
  getTranscript: vi.fn(),
  listTranscriptSpeakers: vi.fn(),
  listTranscriptVersions: vi.fn(),
  mergeTranscriptSegments: vi.fn(),
  redoTranscriptOperation: vi.fn(),
  replaceTranscriptText: vi.fn(),
  restoreTranscriptVersion: vi.fn(),
  searchTranscript: vi.fn(),
  splitTranscriptSegment: vi.fn(),
  batchEditTranscriptSegments: vi.fn(),
  createAssetDownloadUrl: vi.fn(),
  undoTranscriptOperation: vi.fn(),
  listAssetDerivatives: vi.fn(),
  updateTranscriptSpeaker: vi.fn(),
}));

describe("TranscriptViewerPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders a completed transcript after the loading state without hook-order errors", async () => {
    vi.mocked(createAssetDownloadUrl).mockResolvedValue({
      url: "https://media.local/signed/asset-1",
      method: "GET",
      expires_at: "2026-07-07T12:00:00Z",
      headers: {},
    });
    vi.mocked(listAssetDerivatives).mockResolvedValue({ items: [] });
    vi.mocked(listTranscriptSpeakers).mockResolvedValue([]);
    vi.mocked(getTranscript).mockResolvedValue({
      id: "transcript-1",
      job_id: "job-1",
      asset_id: "asset-1",
      language: "en",
      detected_language: "en",
      source_provider: "faster_whisper",
      status: "completed",
      active_version: {
        id: "version-1",
        version_number: 1,
        source: "transcription_provider",
        change_summary: "Initial transcription",
        created_at: "2026-06-27T00:00:00Z",
      },
      created_at: "2026-06-27T00:00:00Z",
      segments: [
        {
          id: "segment-1",
          sequence: 1,
          start_ms: 0,
          end_ms: 1250,
          text: "Hello from the transcript.",
          confidence: null,
          is_unclear: false,
          notes: null,
          speaker_id: "speaker-1",
          speaker_label: "S1",
          word_count: 4,
        },
      ],
    });
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);

    await act(async () => {
      root.render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={["/transcripts/transcript-1"]}>
            <Routes>
              <Route
                path="/transcripts/:transcriptId"
                element={<TranscriptViewerPage />}
              />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(container.textContent).toContain("Transcript review");
    expect(container.textContent).toContain("Hello from the transcript.");
    expect(container.textContent).toContain("S1");
    expect(createAssetDownloadUrl).toHaveBeenCalledWith("asset-1");
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(container.querySelector("audio")?.getAttribute("src")).toBe(
      "https://media.local/signed/asset-1",
    );
    expect(consoleError).not.toHaveBeenCalledWith(
      expect.stringContaining(
        "React has detected a change in the order of Hooks",
      ),
      expect.anything(),
      expect.anything(),
    );

    await act(async () => {
      root.unmount();
    });
    container.remove();
  });

  it("sends editor actions with active version preconditions", async () => {
    const transcript = {
      id: "transcript-1",
      job_id: "job-1",
      asset_id: "asset-1",
      language: "en",
      detected_language: "en",
      source_provider: "faster_whisper",
      status: "completed" as const,
      active_version: {
        id: "version-1",
        version_number: 1,
        source: "transcription_provider",
        change_summary: "Initial transcription",
        created_at: "2026-06-27T00:00:00Z",
      },
      created_at: "2026-06-27T00:00:00Z",
      segments: [
        {
          id: "segment-1",
          sequence: 1,
          start_ms: 0,
          end_ms: 1250,
          text: "Alpha segment.",
          confidence: null,
          is_unclear: false,
          notes: null,
          speaker_id: null,
          word_count: 2,
        },
        {
          id: "segment-2",
          sequence: 2,
          start_ms: 1250,
          end_ms: 2500,
          text: "Beta segment.",
          confidence: null,
          is_unclear: false,
          notes: null,
          speaker_id: null,
          word_count: 2,
        },
      ],
    };
    vi.mocked(getTranscript).mockResolvedValue(transcript);
    vi.mocked(createAssetDownloadUrl).mockResolvedValue({
      url: "https://media.local/signed/asset-1",
      method: "GET",
      expires_at: "2026-07-07T12:00:00Z",
      headers: {},
    });
    vi.mocked(listAssetDerivatives).mockResolvedValue({
      items: [
        {
          id: "derivative-1",
          asset_id: "asset-1",
          kind: "waveform",
          status: "ready",
          content_type: "application/json",
          byte_size: 128,
          metadata: { points: 64 },
          failure_message: null,
          created_at: "2026-07-07T10:00:00Z",
          updated_at: "2026-07-07T10:00:00Z",
        },
      ],
    });
    vi.mocked(searchTranscript).mockResolvedValue({ query: "Alpha", hits: [] });
    vi.mocked(listTranscriptSpeakers).mockResolvedValue([
      {
        id: "speaker-1",
        label: "S1",
        display_name: "Presenter",
        role: null,
        color: "#0f766e",
      },
    ]);
    vi.mocked(assignTranscriptSegmentSpeaker).mockResolvedValue({
      ...transcript,
      segments: [{ ...transcript.segments[0], speaker_id: "speaker-1" }],
    });
    vi.mocked(splitTranscriptSegment).mockResolvedValue(transcript);
    vi.mocked(mergeTranscriptSegments).mockResolvedValue(transcript);
    vi.mocked(annotateTranscriptSegment).mockResolvedValue(transcript);
    vi.mocked(replaceTranscriptText).mockResolvedValue({
      transcript: {
        ...transcript,
        segments: [{ ...transcript.segments[0], text: "Gamma segment." }],
      },
      replacement_count: 1,
    });
    vi.mocked(undoTranscriptOperation).mockResolvedValue(transcript);
    vi.mocked(redoTranscriptOperation).mockResolvedValue(transcript);

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);

    await act(async () => {
      root.render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={["/transcripts/transcript-1"]}>
            <Routes>
              <Route
                path="/transcripts/:transcriptId"
                element={<TranscriptViewerPage />}
              />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    await act(async () => {
      buttonByText(container, "Speakers").click();
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    const speakerSelect = container.querySelector<HTMLSelectElement>(
      'select[aria-label="Assign speaker"]',
    );
    expect(speakerSelect).not.toBeNull();
    await act(async () => {
      speakerSelect!.value = "speaker-1";
      speakerSelect!.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(assignTranscriptSegmentSpeaker).toHaveBeenCalledWith(
      "transcript-1",
      "segment-1",
      {
        base_version_id: "version-1",
        speaker_id: "speaker-1",
      },
    );

    const inputs = Array.from(container.querySelectorAll("input"));
    const searchInput = inputs.find(
      (input) => input.placeholder === "Type to search for a word or phrase",
    );
    const replaceInput = inputs.find(
      (input) => input.placeholder === "Replacement text",
    );
    expect(searchInput).toBeTruthy();
    expect(replaceInput).toBeTruthy();
    await act(async () => {
      searchInput!.value = "Alpha";
      searchInput!.dispatchEvent(new Event("input", { bubbles: true }));
      replaceInput!.value = "Gamma";
      replaceInput!.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      buttonByText(container, "Replace all").click();
    });
    expect(replaceTranscriptText).toHaveBeenCalledWith("transcript-1", {
      base_version_id: "version-1",
      query: "Alpha",
      replacement: "Gamma",
      replace_all: true,
    });

    await act(async () => {
      window.dispatchEvent(
        new KeyboardEvent("keydown", { key: "z", ctrlKey: true }),
      );
    });
    expect(undoTranscriptOperation).toHaveBeenCalledWith("transcript-1", {
      base_version_id: "version-1",
    });

    await act(async () => {
      window.dispatchEvent(
        new KeyboardEvent("keydown", { key: "y", ctrlKey: true }),
      );
    });
    expect(redoTranscriptOperation).toHaveBeenCalledWith("transcript-1", {
      base_version_id: "version-1",
    });

    await act(async () => {
      window.dispatchEvent(
        new KeyboardEvent("keydown", {
          key: "S",
          ctrlKey: true,
          shiftKey: true,
        }),
      );
    });
    expect(splitTranscriptSegment).toHaveBeenCalledWith(
      "transcript-1",
      "segment-1",
      625,
      "version-1",
    );

    await act(async () => {
      window.dispatchEvent(
        new KeyboardEvent("keydown", { key: "m", ctrlKey: true }),
      );
    });
    expect(mergeTranscriptSegments).toHaveBeenCalledWith(
      "transcript-1",
      "segment-1",
      "segment-2",
      "version-1",
    );

    await act(async () => {
      window.dispatchEvent(
        new KeyboardEvent("keydown", {
          key: "U",
          ctrlKey: true,
          shiftKey: true,
        }),
      );
    });
    expect(annotateTranscriptSegment).toHaveBeenCalledWith(
      "transcript-1",
      "segment-1",
      {
        base_version_id: "version-1",
        is_unclear: true,
      },
    );

    await act(async () => {
      window.dispatchEvent(
        new KeyboardEvent("keydown", { key: "1", altKey: true }),
      );
    });
    expect(assignTranscriptSegmentSpeaker).toHaveBeenLastCalledWith(
      "transcript-1",
      "segment-1",
      {
        base_version_id: "version-1",
        speaker_id: "speaker-1",
      },
    );

    await act(async () => {
      root.unmount();
    });
    container.remove();
  });

  it("exports only selected transcript segments", async () => {
    const transcript = {
      id: "transcript-1",
      job_id: "job-1",
      asset_id: "asset-1",
      language: "en",
      detected_language: "en",
      source_provider: "faster_whisper",
      status: "completed" as const,
      active_version: {
        id: "version-1",
        version_number: 1,
        source: "transcription_provider",
        change_summary: "Initial transcription",
        created_at: "2026-06-27T00:00:00Z",
      },
      created_at: "2026-06-27T00:00:00Z",
      segments: [
        {
          id: "segment-1",
          sequence: 1,
          start_ms: 0,
          end_ms: 1250,
          text: "Do not export.",
          confidence: null,
          is_unclear: false,
          notes: null,
          speaker_id: null,
          word_count: 3,
        },
        {
          id: "segment-2",
          sequence: 2,
          start_ms: 1250,
          end_ms: 2500,
          text: "Export this.",
          confidence: null,
          is_unclear: false,
          notes: null,
          speaker_id: null,
          word_count: 2,
        },
      ],
    };
    vi.mocked(getTranscript).mockResolvedValue(transcript);
    vi.mocked(createAssetDownloadUrl).mockResolvedValue({
      url: "https://media.local/signed/asset-1",
      method: "GET",
      expires_at: "2026-07-07T12:00:00Z",
      headers: {},
    });
    vi.mocked(listAssetDerivatives).mockResolvedValue({ items: [] });
    vi.mocked(listTranscriptSpeakers).mockResolvedValue([]);
    vi.mocked(createExport).mockResolvedValue({
      id: "export-1",
      transcript_version_id: "version-1",
      format: "txt",
      status: "queued",
      error_message: null,
      created_at: "2026-07-07T00:00:00Z",
      expires_at: "2026-07-14T00:00:00Z",
    });

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);

    await act(async () => {
      root.render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={["/transcripts/transcript-1"]}>
            <Routes>
              <Route
                path="/transcripts/:transcriptId"
                element={<TranscriptViewerPage />}
              />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    const secondSegmentCheckbox = container.querySelector<HTMLInputElement>(
      'input[aria-label="Select segment 2 for export"]',
    );
    expect(secondSegmentCheckbox).not.toBeNull();
    await act(async () => {
      secondSegmentCheckbox!.click();
    });
    await act(async () => {
      buttonByText(container, "TXT").click();
    });

    expect(createExport).toHaveBeenCalledWith({
      source_type: "transcript",
      transcript_id: "transcript-1",
      format: "txt",
      segment_ids: ["segment-2"],
      options: {},
    });

    await act(async () => {
      root.unmount();
    });
    container.remove();
  });
});

function buttonByText(
  container: HTMLElement,
  label: string,
): HTMLButtonElement {
  const button = Array.from(container.querySelectorAll("button")).find(
    (candidate) => candidate.textContent?.includes(label),
  );
  if (!button) throw new Error(`Could not find button: ${label}`);
  return button;
}
