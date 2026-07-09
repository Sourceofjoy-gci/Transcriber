import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { App } from "./App";
import {
  getCurrentSession,
  listApiProviders,
  listInstalledModels,
  listOrganisations,
  listProjects,
} from "./lib/api";

vi.mock("./lib/api", async () => {
  const actual = await vi.importActual<typeof import("./lib/api")>("./lib/api");
  return {
    ...actual,
    getCurrentSession: vi.fn(),
    listApiProviders: vi.fn(),
    listInstalledModels: vi.fn(),
    listOrganisations: vi.fn(),
    listProjects: vi.fn(),
    logout: vi.fn(),
  };
});

describe("UploadPage", () => {
  afterEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
  });

  it("shows enabled API transcription providers with an egress acknowledgement control", async () => {
    vi.mocked(getCurrentSession).mockResolvedValue({
      user: {
        id: "user-1",
        email: "admin@example.com",
        display_name: "Admin User",
        is_active: true,
        last_login_at: null,
      },
      memberships: [
        {
          organisation_id: "org-1",
          role_code: "organisation_administrator",
          status: "active",
        },
      ],
      csrf_token: "csrf-token",
    });
    vi.mocked(listInstalledModels).mockResolvedValue([]);
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
    vi.mocked(listOrganisations).mockResolvedValue([
      {
        id: "org-1",
        name: "Local Organisation",
        slug: "local-organisation",
        external_apis_allowed: true,
        local_only_enforced: false,
        retention_days: null,
        role_code: "organisation_administrator",
        is_current: true,
      },
    ]);
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
        capabilities: { tasks: ["transcription"] },
        enabled: true,
        is_default: false,
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
          <MemoryRouter initialEntries={["/upload"]}>
            <App />
          </MemoryRouter>
        </QueryClientProvider>,
      );
    });
    await flushPromises();
    await flushPromises();

    const targetSelect = Array.from(container.querySelectorAll("select")).find(
      (select) =>
        Array.from(select.options).some(
          (option) => option.value === "api_provider",
        ),
    );
    expect(targetSelect).toBeTruthy();
    expect(container.textContent).toContain("Speaker diarisation");
    expect(container.textContent).toContain("Expected speakers");
    expect(container.textContent).toContain("Legal Discovery");

    await act(async () => {
      targetSelect!.value = "api_provider";
      targetSelect!.dispatchEvent(new Event("change", { bubbles: true }));
    });

    expect(container.textContent).toContain("OpenAI Whisper");
    expect(container.textContent).toContain(
      "I acknowledge this transcription sends media to the selected provider",
    );

    await act(async () => {
      root.unmount();
    });
    container.remove();
  });
});

async function flushPromises(): Promise<void> {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}
