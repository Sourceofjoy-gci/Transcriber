import { describe, expect, it, vi, beforeEach } from "vitest";

import {
  ApiError,
  getActiveOrganisationId,
  setActiveOrganisationId,
} from "./api";

describe("api helpers", () => {
  beforeEach(() => {
    vi.resetModules();
    sessionStorage.clear();
    document.cookie = "csrf_token=; Max-Age=0; path=/";
    vi.restoreAllMocks();
  });

  it("stores and retrieves the active organisation id", () => {
    setActiveOrganisationId("org-123");
    expect(getActiveOrganisationId()).toBe("org-123");
  });

  it("ApiError preserves status code and message", () => {
    const error = new ApiError(404, "Not found");
    expect(error).toBeInstanceOf(Error);
    expect(error.status).toBe(404);
    expect(error.message).toBe("Not found");
  });
});

describe("request error extraction", async () => {
  it("parses JSON error detail", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Invalid input" }), {
        status: 400,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { login } = await import("./api");
    sessionStorage.clear();
    await expect(
      login("user@example.com", "valid-password-1234"),
    ).rejects.toMatchObject({ status: 400, message: "Invalid input" });
  });

  it("refreshes an expired session and retries the original request", async () => {
    document.cookie = "csrf_token=csrf-refresh; path=/";
    const session = {
      user: {
        id: "user-1",
        email: "admin@example.com",
        display_name: "Admin",
        is_active: true,
      },
      memberships: [
        {
          organisation_id: "org-1",
          role_code: "system_administrator",
          status: "active",
        },
      ],
      csrf_token: "csrf-new",
    };
    const installedModels = [
      {
        id: "installed-1",
        catalog_id: "catalog-1",
        status: "available",
        enabled: false,
        download_progress: 0,
        last_error: null,
        catalog: {
          id: "catalog-1",
          adapter_key: "faster_whisper",
          model_identifier: "base",
          name: "Faster-Whisper Base",
          model_type: "transcription",
          size_bytes: null,
          requirements: {},
          capabilities: {},
        },
      },
    ];
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: "Invalid or expired session" }), {
          status: 401,
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(session), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(installedModels), { status: 200 }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const { listInstalledModels } = await import("./api");

    await expect(listInstalledModels()).resolves.toEqual(installedModels);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/installed-models");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/v1/auth/refresh");
    expect(fetchMock.mock.calls[2][0]).toBe("/api/v1/installed-models");
    expect(
      new Headers(fetchMock.mock.calls[1][1]?.headers).get("X-CSRF-Token"),
    ).toBe("csrf-refresh");
    expect(sessionStorage.getItem("activeOrganisationId")).toBe("org-1");
  });

  it("creates a transcription job with the selected local model target", async () => {
    document.cookie = "csrf_token=csrf-job; path=/";
    setActiveOrganisationId("org-1");
    const job = {
      id: "job-1",
      asset_id: "asset-1",
      status: "queued",
      progress_percent: 0,
      execution_target_kind: "local_model",
      execution_target_id: "model-1",
      language: "en",
      error_code: null,
      error_message: null,
      created_at: "2026-06-27T00:00:00Z",
      started_at: null,
      finished_at: null,
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(job), { status: 202 }));
    vi.stubGlobal("fetch", fetchMock);

    const { createAutomaticJob } = await import("./api");

    await expect(
      createAutomaticJob("asset-1", {
        execution_target_kind: "local_model",
        execution_target_id: "model-1",
        language: "en",
        options: { word_timestamps: true },
      }),
    ).resolves.toEqual(job);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/transcription-jobs",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          asset_id: "asset-1",
          execution_target_kind: "local_model",
          execution_target_id: "model-1",
          language: "en",
          options: { word_timestamps: true },
        }),
      }),
    );
    const headers = new Headers(fetchMock.mock.calls[0][1]?.headers);
    expect(headers.get("X-Organisation-ID")).toBe("org-1");
    expect(headers.get("X-CSRF-Token")).toBe("csrf-job");
  });

  it("creates API-provider transcription jobs with egress acknowledgement", async () => {
    document.cookie = "csrf_token=csrf-job; path=/";
    setActiveOrganisationId("org-1");
    const job = {
      id: "job-1",
      asset_id: "asset-1",
      status: "queued",
      progress_percent: 0,
      execution_target_kind: "api_provider",
      execution_target_id: "provider-1",
      language: "en",
      error_code: null,
      error_message: null,
      created_at: "2026-07-06T00:00:00Z",
      started_at: null,
      finished_at: null,
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(job), { status: 202 }));
    vi.stubGlobal("fetch", fetchMock);

    const { createAutomaticJob } = await import("./api");

    await expect(
      createAutomaticJob("asset-1", {
        execution_target_kind: "api_provider",
        execution_target_id: "provider-1",
        egress_acknowledged: true,
        language: "en",
        options: { word_timestamps: true },
      }),
    ).resolves.toEqual(job);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/transcription-jobs",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          asset_id: "asset-1",
          execution_target_kind: "api_provider",
          execution_target_id: "provider-1",
          egress_acknowledged: true,
          language: "en",
          options: { word_timestamps: true },
        }),
      }),
    );
  });

  it("creates an API provider using the backend provider contract", async () => {
    document.cookie = "csrf_token=csrf-provider; path=/";
    setActiveOrganisationId("org-1");
    const provider = {
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
      enabled: false,
      is_default: false,
      secret_configured: true,
      timeout_seconds: 120,
      retry_limit: 2,
      last_tested_at: null,
      last_error: null,
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify(provider), { status: 201 }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const { createApiProvider } = await import("./api");

    await expect(
      createApiProvider({
        adapter_key: "openai_compatible",
        name: "OpenAI Whisper",
        category: "transcription",
        base_url: "https://api.example.com",
        endpoint_path: "/v1/audio/transcriptions",
        model_name: "whisper-1",
        auth_type: "bearer",
        headers: {},
        capabilities: {},
        timeout_seconds: 120,
        retry_limit: 2,
        api_key: "sk-test",
      } as never),
    ).resolves.toEqual(provider);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/api-providers",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          adapter_key: "openai_compatible",
          name: "OpenAI Whisper",
          category: "transcription",
          base_url: "https://api.example.com",
          endpoint_path: "/v1/audio/transcriptions",
          model_name: "whisper-1",
          auth_type: "bearer",
          headers: {},
          capabilities: {},
          timeout_seconds: 120,
          retry_limit: 2,
          api_key: "sk-test",
        }),
      }),
    );
  });

  it("updates an API provider using the backend provider contract", async () => {
    document.cookie = "csrf_token=csrf-provider; path=/";
    const provider = {
      id: "provider-1",
      adapter_key: "generic_rest_transcription",
      name: "Generic API",
      category: "transcription",
      base_url: "https://api.example.com",
      endpoint_path: "/transcribe",
      model_name: "fast-model",
      auth_type: "api_key",
      headers: {},
      capabilities: {},
      enabled: true,
      is_default: false,
      secret_configured: true,
      timeout_seconds: 90,
      retry_limit: 1,
      last_tested_at: null,
      last_error: null,
    };
    const payload = {
      adapter_key: "generic_rest_transcription" as const,
      name: "Generic API",
      category: "transcription",
      base_url: "https://api.example.com",
      endpoint_path: "/transcribe",
      model_name: "fast-model",
      auth_type: "api_key" as const,
      headers: {},
      capabilities: {},
      timeout_seconds: 90,
      retry_limit: 1,
      api_key: "sk-updated",
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify(provider), { status: 200 }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const { updateApiProvider } = await import("./api");

    await expect(updateApiProvider("provider-1", payload)).resolves.toEqual(
      provider,
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/api-providers/provider-1",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    );
  });

  it("rotates API provider secrets using api_key", async () => {
    document.cookie = "csrf_token=csrf-provider; path=/";
    const provider = {
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
      enabled: false,
      is_default: false,
      secret_configured: true,
      timeout_seconds: 120,
      retry_limit: 2,
      last_tested_at: null,
      last_error: null,
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify(provider), { status: 200 }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const { rotateApiProviderSecret } = await import("./api");

    await expect(
      rotateApiProviderSecret("provider-1", "sk-new"),
    ).resolves.toEqual(provider);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/api-providers/provider-1/rotate-secret",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ api_key: "sk-new" }),
      }),
    );
  });

  it("fetches job event history from the JSON history endpoint", async () => {
    const events = [
      {
        id: "event-1",
        sequence: 1,
        state: "queued",
        progress_percent: 0,
        message: "Queued",
        data: {},
        created_at: "2026-07-06T00:00:00Z",
      },
    ];
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(events), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const { listJobEvents } = await import("./api");

    await expect(listJobEvents("job-1")).resolves.toEqual(events);
    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/v1/transcription-jobs/job-1/events/history",
    );
  });

  it("creates source-aware exports with selected segment ids", async () => {
    document.cookie = "csrf_token=csrf-export; path=/";
    const exportRecord = {
      id: "export-1",
      transcript_version_id: "version-1",
      format: "txt",
      status: "queued",
      error_message: null,
      created_at: "2026-07-07T00:00:00Z",
      expires_at: "2026-07-14T00:00:00Z",
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify(exportRecord), { status: 202 }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const { createExport } = await import("./api");

    await expect(
      createExport({
        source_type: "transcript",
        transcript_id: "transcript-1",
        format: "txt",
        segment_ids: ["segment-2"],
        options: { include_timestamps: false },
      }),
    ).resolves.toEqual(exportRecord);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/exports",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          source_type: "transcript",
          transcript_id: "transcript-1",
          format: "txt",
          segment_ids: ["segment-2"],
          options: { include_timestamps: false },
        }),
      }),
    );
  });
});
