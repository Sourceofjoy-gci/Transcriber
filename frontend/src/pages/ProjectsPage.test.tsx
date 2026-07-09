import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ProjectsPage } from "./ProjectsPage";
import {
  createProject,
  deleteProject,
  listProjects,
  updateProject,
} from "../lib/api";

vi.mock("../lib/api", () => ({
  ApiError: class ApiError extends Error {},
  createProject: vi.fn(),
  deleteProject: vi.fn(),
  listProjects: vi.fn(),
  updateProject: vi.fn(),
}));

describe("ProjectsPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders projects and exposes create/update/delete actions", async () => {
    vi.mocked(listProjects).mockResolvedValue([
      {
        id: "project-1",
        name: "Legal Discovery",
        description: "Case audio",
        sensitivity: "restricted",
        retention_days: 365,
        external_apis_allowed: false,
        created_at: "2026-07-07T00:00:00Z",
      },
    ]);
    vi.mocked(createProject).mockResolvedValue({} as never);
    vi.mocked(updateProject).mockResolvedValue({} as never);
    vi.mocked(deleteProject).mockResolvedValue(undefined);

    const { container, root } = await renderPage(<ProjectsPage />);

    expect(container.textContent).toContain("Projects");
    expect(container.textContent).toContain("Legal Discovery");
    await act(async () => buttonByText(container, "Save project").click());
    expect(createProject).toHaveBeenCalled();
    await act(async () => buttonByText(container, "Archive").click());
    expect(vi.mocked(deleteProject).mock.calls[0][0]).toBe("project-1");

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
  await act(async () =>
    root.render(
      <QueryClientProvider client={queryClient}>{element}</QueryClientProvider>,
    ),
  );
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)));
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
