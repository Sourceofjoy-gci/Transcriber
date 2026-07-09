import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AssetsPage } from "./AssetsPage";
import {
  createAssetDownloadUrl,
  deleteAsset,
  listAssets,
  listProjects,
} from "../lib/api";

vi.mock("../lib/api", () => ({
  ApiError: class ApiError extends Error {},
  createAssetDownloadUrl: vi.fn(),
  deleteAsset: vi.fn(),
  listAssets: vi.fn(),
  listProjects: vi.fn(),
}));

describe("AssetsPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders project-aware asset filters and actions", async () => {
    vi.mocked(listProjects).mockResolvedValue([
      {
        id: "project-1",
        name: "Legal Discovery",
        description: null,
        sensitivity: "restricted",
        retention_days: 365,
        external_apis_allowed: false,
        created_at: "2026-07-07T00:00:00Z",
      },
    ]);
    vi.mocked(listAssets).mockResolvedValue({
      items: [
        {
          id: "asset-1",
          project_id: "project-1",
          original_filename: "meeting-alpha.wav",
          content_type: "audio/wav",
          byte_size: 4096,
          sha256: "a".repeat(64),
          status: "ready",
          failure_code: null,
          failure_message: null,
          created_at: "2026-07-07T00:00:00Z",
          metadata: {
            duration_ms: 60000,
            container: "wav",
            audio_codec: "pcm",
            video_codec: null,
            sample_rate_hz: 16000,
            channels: 1,
            bit_rate: null,
          },
        },
      ],
      next_offset: null,
    });
    vi.mocked(createAssetDownloadUrl).mockResolvedValue({
      url: "/api/v1/assets/asset-1/download",
      method: "GET",
      expires_at: "2026-07-07T01:00:00Z",
      headers: {},
    });
    vi.mocked(deleteAsset).mockResolvedValue(undefined);

    const { container, root } = await renderPage(<AssetsPage />);

    expect(container.textContent).toContain("Asset Library");
    expect(container.textContent).toContain("meeting-alpha.wav");
    expect(container.textContent).toContain("Legal Discovery");

    await act(async () => {
      buttonByText(container, "Download").click();
    });
    expect(vi.mocked(createAssetDownloadUrl).mock.calls[0][0]).toBe("asset-1");

    await act(async () => {
      buttonByText(container, "Delete").click();
    });
    expect(vi.mocked(deleteAsset).mock.calls[0][0]).toBe("asset-1");

    await act(async () => root.unmount());
    container.remove();
  });
});

async function renderPage(
  element: React.ReactElement,
): Promise<{ container: HTMLElement; root: ReturnType<typeof createRoot> }> {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(
      <QueryClientProvider client={queryClient}>{element}</QueryClientProvider>,
    );
  });
  await flushPromises();
  return { container, root };
}

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

async function flushPromises(): Promise<void> {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}
