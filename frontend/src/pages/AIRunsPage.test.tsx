import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AIRunsPage } from "./AIRunsPage";
import {
  cancelAIRun,
  getAIRun,
  listAIRuns,
  listApiProviders,
  listTranscripts,
  retryAIRun,
} from "../lib/api";

vi.mock("../lib/api", () => ({
  ApiError: class ApiError extends Error {},
  cancelAIRun: vi.fn(),
  createAIRun: vi.fn(),
  getAIRun: vi.fn(),
  listAIRuns: vi.fn(),
  listApiProviders: vi.fn(),
  listTranscripts: vi.fn(),
  retryAIRun: vi.fn(),
}));

describe("AIRunsPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders backend run history with target progress and controls", async () => {
    vi.mocked(listTranscripts).mockResolvedValue([
      {
        id: "transcript-1",
        job_id: "job-1",
        asset_id: "asset-1",
        language: "en",
        detected_language: "en",
        source_provider: "faster_whisper",
        status: "completed",
        active_version: null,
        created_at: "2026-07-06T00:00:00Z",
      },
    ]);
    vi.mocked(listApiProviders).mockResolvedValue([
      {
        id: "provider-1",
        adapter_key: "openai_compatible",
        name: "AI Provider",
        category: "post_processing",
        base_url: "https://api.example.test",
        endpoint_path: "/v1/chat/completions",
        model_name: "gpt-test",
        auth_type: "bearer",
        headers: {},
        capabilities: { tasks: ["summary", "clean"] },
        enabled: true,
        is_default: false,
        secret_configured: true,
        timeout_seconds: 120,
        retry_limit: 2,
        last_error: null,
        last_tested_at: null,
      },
    ]);
    vi.mocked(listAIRuns).mockResolvedValue([
      {
        id: "run-1",
        status: "running",
        task: "summary",
        transcript_id: "transcript-1",
        transcript_version_id: "version-1",
        execution_target_kind: "api_provider",
        execution_target_id: "provider-1",
        progress_percent: 40,
        progress_message: "Calling provider",
        result: null,
        error_message: null,
        created_at: "2026-07-06T01:00:00Z",
        completed_at: null,
      },
      {
        id: "run-2",
        status: "failed",
        task: "clean",
        transcript_id: "transcript-1",
        transcript_version_id: "version-1",
        execution_target_kind: "automatic",
        execution_target_id: null,
        progress_percent: 0,
        progress_message: "Failed",
        result: null,
        error_message: "Provider unavailable",
        created_at: "2026-07-06T00:30:00Z",
        completed_at: "2026-07-06T00:31:00Z",
      },
    ]);
    vi.mocked(cancelAIRun).mockResolvedValue({
      id: "run-1",
      status: "cancelled",
      task: "summary",
      transcript_id: "transcript-1",
      transcript_version_id: "version-1",
      execution_target_kind: "api_provider",
      execution_target_id: "provider-1",
      progress_percent: 40,
      progress_message: "Cancelled",
      result: null,
      error_message: null,
      created_at: "2026-07-06T01:00:00Z",
      completed_at: "2026-07-06T01:01:00Z",
    });
    vi.mocked(retryAIRun).mockResolvedValue({
      id: "run-2",
      status: "queued",
      task: "clean",
      transcript_id: "transcript-1",
      transcript_version_id: "version-1",
      execution_target_kind: "automatic",
      execution_target_id: null,
      progress_percent: 0,
      progress_message: "Queued for retry",
      result: null,
      error_message: null,
      created_at: "2026-07-06T00:30:00Z",
      completed_at: null,
    });
    vi.mocked(getAIRun).mockResolvedValue({
      id: "run-2",
      status: "queued",
      task: "clean",
      transcript_id: "transcript-1",
      transcript_version_id: "version-1",
      execution_target_kind: "automatic",
      execution_target_id: null,
      progress_percent: 0,
      progress_message: "Queued for retry",
      result: null,
      error_message: null,
      created_at: "2026-07-06T00:30:00Z",
      completed_at: null,
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
          <AIRunsPage />
        </QueryClientProvider>,
      );
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(listAIRuns).toHaveBeenCalled();
    expect(container.textContent).toContain("Run history");
    expect(container.textContent).toContain("AI Provider");
    expect(container.textContent).toContain("40%");
    expect(container.textContent).toContain("Calling provider");
    expect(container.textContent).toContain("Provider unavailable");

    await act(async () => {
      buttonByText(container, "Cancel").click();
    });
    expect(cancelAIRun).toHaveBeenCalledWith("run-1");

    await act(async () => {
      buttonsByText(container, "Retry").at(-1)!.click();
    });
    expect(retryAIRun).toHaveBeenCalledWith("run-2");

    await act(async () => {
      root.unmount();
    });
    container.remove();
  });
});

function buttonsByText(
  container: HTMLElement,
  label: string,
): HTMLButtonElement[] {
  return Array.from(container.querySelectorAll("button")).filter((candidate) =>
    candidate.textContent?.includes(label),
  );
}

function buttonByText(
  container: HTMLElement,
  label: string,
): HTMLButtonElement {
  const button = buttonsByText(container, label)[0];
  if (!button) throw new Error(`Could not find button: ${label}`);
  return button;
}
