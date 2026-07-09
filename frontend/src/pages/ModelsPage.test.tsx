import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ModelsPage } from "./ModelsPage";
import {
  cancelInstalledModelDownload,
  createModelCatalogEntry,
  listInstalledModels,
  listModelCatalog,
  putTaskDefault,
} from "../lib/api";

vi.mock("../lib/api", () => ({
  ApiError: class ApiError extends Error {},
  addInstalledModel: vi.fn(),
  cancelInstalledModelDownload: vi.fn(),
  createModelCatalogEntry: vi.fn(),
  deleteInstalledModel: vi.fn(),
  disableInstalledModel: vi.fn(),
  downloadInstalledModel: vi.fn(),
  enableInstalledModel: vi.fn(),
  listInstalledModels: vi.fn(),
  listModelCatalog: vi.fn(),
  putTaskDefault: vi.fn(),
  testInstalledModel: vi.fn(),
}));

describe("ModelsPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders compatibility controls and model administration actions", async () => {
    vi.mocked(listModelCatalog).mockResolvedValue([
      {
        id: "catalog-1",
        adapter_key: "whisper_cpp",
        model_identifier: "ggml-tiny.bin",
        name: "Whisper.cpp Tiny",
        model_type: "transcription",
        source_url:
          "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin",
        revision: null,
        size_bytes: 77691713,
        requirements: { recommended_device: "cpu" },
        capabilities: { tasks: ["transcription"] },
        checksum:
          "sha256:be07e048e1e599ad46341c8d2a135645097a538221678b7acdd1b1919c6e1b21",
      },
      {
        id: "catalog-2",
        adapter_key: "faster_whisper",
        model_identifier: "Systran/faster-whisper-large-v3",
        name: "Faster-Whisper Large v3",
        model_type: "transcription",
        source_url: "https://huggingface.co/Systran/faster-whisper-large-v3",
        revision: null,
        size_bytes: 3100000000,
        requirements: { recommended_device: "cuda" },
        capabilities: { tasks: ["transcription"] },
        checksum: null,
      },
    ]);
    vi.mocked(listInstalledModels).mockResolvedValue([
      {
        id: "installed-1",
        catalog_id: "catalog-1",
        status: "installed",
        enabled: true,
        download_progress: 100,
        storage_key: "organisations/org/models/ggml-tiny.bin",
        verified_at: "2026-07-07T00:00:00Z",
        last_error: null,
        hardware_compatibility: {
          compatible: true,
          recommendations: ["CPU model is ready"],
          worker_labels: ["cpu"],
        },
        is_default: false,
        catalog: {
          id: "catalog-1",
          adapter_key: "whisper_cpp",
          model_identifier: "ggml-tiny.bin",
          name: "Whisper.cpp Tiny",
          model_type: "transcription",
          source_url: null,
          revision: null,
          size_bytes: null,
          requirements: {},
          capabilities: {},
          checksum: null,
        },
      },
      {
        id: "installed-2",
        catalog_id: "catalog-2",
        status: "downloading",
        enabled: false,
        download_progress: 45,
        storage_key: null,
        verified_at: null,
        last_error: null,
        hardware_compatibility: {
          compatible: false,
          reasons: ["Requires CUDA GPU"],
          worker_labels: ["cpu"],
        },
        is_default: false,
        catalog: {
          id: "catalog-2",
          adapter_key: "faster_whisper",
          model_identifier: "Systran/faster-whisper-large-v3",
          name: "Faster-Whisper Large v3",
          model_type: "transcription",
          source_url: null,
          revision: null,
          size_bytes: null,
          requirements: {},
          capabilities: {},
          checksum: null,
        },
      },
    ]);
    vi.mocked(putTaskDefault).mockResolvedValue({} as never);
    vi.mocked(cancelInstalledModelDownload).mockResolvedValue({} as never);
    vi.mocked(createModelCatalogEntry).mockResolvedValue({} as never);

    const { container, root } = await renderPage(<ModelsPage />);

    expect(container.textContent).toContain("Whisper.cpp Tiny");
    expect(container.textContent).toContain("Requires CUDA GPU");
    expect(container.textContent).toContain("worker: cpu");

    await act(async () => {
      buttonByText(container, "Set default").click();
    });
    expect(vi.mocked(putTaskDefault).mock.calls[0][0]).toBe("installed-1");

    await act(async () => {
      buttonByText(container, "Cancel").click();
    });
    expect(vi.mocked(cancelInstalledModelDownload).mock.calls[0][0]).toBe(
      "installed-2",
    );

    await act(async () => {
      setInput(container, "custom-name", "Custom Legal Model");
      setInput(container, "custom-identifier", "custom/legal.bin");
      setInput(
        container,
        "custom-source-url",
        "https://models.example.com/legal.bin",
      );
      setInput(container, "custom-checksum", "sha256:" + "b".repeat(64));
    });
    await act(async () => {
      container
        .querySelector("form")
        ?.dispatchEvent(
          new Event("submit", { bubbles: true, cancelable: true }),
        );
    });
    expect(vi.mocked(createModelCatalogEntry).mock.calls[0][0]).toEqual(
      expect.objectContaining({
        name: "Custom Legal Model",
        model_identifier: "custom/legal.bin",
        source_url: "https://models.example.com/legal.bin",
      }),
    );

    await act(async () => {
      root.unmount();
    });
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

function setInput(container: HTMLElement, name: string, value: string): void {
  const input = container.querySelector(
    `[name="${name}"]`,
  ) as HTMLInputElement | null;
  if (!input) throw new Error(`Could not find input: ${name}`);
  const setter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype,
    "value",
  )?.set;
  setter?.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

async function flushPromises(): Promise<void> {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}
