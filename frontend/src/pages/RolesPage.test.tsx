import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { RolesPage } from "./RolesPage";
import {
  createRole,
  deleteRole,
  listPermissions,
  listRoles,
  updateRole,
} from "../lib/api";

vi.mock("../lib/api", () => ({
  ApiError: class ApiError extends Error {},
  createRole: vi.fn(),
  deleteRole: vi.fn(),
  listPermissions: vi.fn(),
  listRoles: vi.fn(),
  updateRole: vi.fn(),
}));

describe("RolesPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders permissions and custom role controls", async () => {
    vi.mocked(listPermissions).mockResolvedValue([
      { id: "perm-1", code: "assets.read", description: "View media files" },
      {
        id: "perm-2",
        code: "transcripts.read",
        description: "View transcripts",
      },
    ]);
    vi.mocked(listRoles).mockResolvedValue([
      {
        id: "role-1",
        code: "legal_reviewer",
        name: "Legal Reviewer",
        is_system: false,
        permissions: ["assets.read"],
      },
    ]);
    vi.mocked(createRole).mockResolvedValue({} as never);
    vi.mocked(updateRole).mockResolvedValue({} as never);
    vi.mocked(deleteRole).mockResolvedValue(undefined);

    const { container, root } = await renderPage(<RolesPage />);

    expect(container.textContent).toContain("Roles");
    expect(container.textContent).toContain("Legal Reviewer");
    expect(container.textContent).toContain("assets.read");
    await act(async () => buttonByText(container, "Create role").click());
    expect(createRole).toHaveBeenCalled();
    await act(async () => buttonByText(container, "Delete").click());
    expect(vi.mocked(deleteRole).mock.calls[0][0]).toBe("role-1");

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
