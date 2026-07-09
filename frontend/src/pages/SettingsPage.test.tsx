import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { SettingsPage } from "./SettingsPage";
import {
  getHardwareCapabilities,
  getStructuredSettings,
  listInstalledModels,
  putStructuredSettings,
  putTaskDefault,
} from "../lib/api";

vi.mock("../lib/api", () => ({
  ApiError: class ApiError extends Error {},
  deleteSetting: vi.fn(),
  getHardwareCapabilities: vi.fn(),
  getStructuredSettings: vi.fn(),
  listInstalledModels: vi.fn(),
  putSetting: vi.fn(),
  putStructuredSettings: vi.fn(),
  putTaskDefault: vi.fn(),
}));

describe("SettingsPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("allows the transcription default model to be selected by installed model id", async () => {
    const structuredSettings = {
      organisation: {
        id: "org-1",
        name: "Local Organisation",
        retention_days: 30,
        external_apis_allowed: true,
        local_only_enforced: false,
      },
      upload: { max_upload_bytes: 2147483648 },
      queue: { max_concurrent_jobs: 2 },
      ai: { default_report_template_kind: "presentation" },
    };
    vi.mocked(getStructuredSettings).mockResolvedValue(structuredSettings);
    vi.mocked(getHardwareCapabilities).mockResolvedValue({
      cpu_cores: 8,
      total_memory_bytes: 16 * 1024 ** 3,
      has_cuda: false,
      has_metal: false,
      detected_gpus: [],
    });
    vi.mocked(listInstalledModels).mockResolvedValue([
      {
        id: "installed-1",
        catalog_id: "catalog-1",
        status: "installed",
        enabled: true,
        download_progress: 100,
        storage_key: "organisations/org/models/tiny",
        verified_at: null,
        last_error: null,
        hardware_compatibility: { compatible: true },
        is_default: true,
        catalog: {
          id: "catalog-1",
          adapter_key: "faster_whisper",
          model_identifier: "Systran/faster-whisper-tiny",
          name: "Faster-Whisper Tiny",
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
    vi.mocked(putStructuredSettings).mockResolvedValue(structuredSettings);

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
          <SettingsPage />
        </QueryClientProvider>,
      );
    });
    await flushPromises();

    expect(container.textContent).toContain("Default transcription model");
    expect(container.textContent).toContain("Faster-Whisper Tiny");
    expect(container.textContent).toContain("Upload limits");
    expect(container.textContent).toContain("Queue defaults");

    await act(async () => {
      buttonByText(container, "Save default").click();
    });

    expect(vi.mocked(putTaskDefault).mock.calls[0][0]).toBe("installed-1");

    await act(async () => {
      buttonByText(container, "Save settings").click();
    });
    expect(putStructuredSettings).toHaveBeenCalled();

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

async function flushPromises(): Promise<void> {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}
