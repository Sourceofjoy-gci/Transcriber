import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ProvidersPage } from "./ProvidersPage";
import { listApiProviders } from "../lib/api";

vi.mock("../lib/api", () => ({
  ApiError: class ApiError extends Error {},
  createApiProvider: vi.fn(),
  deleteApiProvider: vi.fn(),
  disableApiProvider: vi.fn(),
  enableApiProvider: vi.fn(),
  getApiProviderUsage: vi.fn(),
  listApiProviders: vi.fn(),
  rotateApiProviderSecret: vi.fn(),
  setDefaultApiProvider: vi.fn(),
  testApiProvider: vi.fn(),
}));

describe("ProvidersPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders providers returned with backend field names", async () => {
    vi.mocked(listApiProviders).mockResolvedValue([
      {
        id: "provider-1",
        adapter_key: "openai_compatible",
        name: "OpenAI Whisper",
        category: "transcription",
        base_url: "https://api.example.com",
        endpoint_path: "/v1/audio/transcriptions",
        model_name: "whisper-1",
        auth_type: "bearer",
        headers: {},
        capabilities: {},
        enabled: true,
        is_default: true,
        secret_configured: true,
        timeout_seconds: 120,
        retry_limit: 2,
        last_tested_at: null,
        last_error: null,
      },
    ]);
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
          <ProvidersPage />
        </QueryClientProvider>,
      );
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(container.textContent).toContain("OpenAI Whisper");
    expect(container.textContent).toContain("openai compatible");
    expect(container.textContent).toContain("Enabled");

    await act(async () => {
      root.unmount();
    });
    container.remove();
  });
});
