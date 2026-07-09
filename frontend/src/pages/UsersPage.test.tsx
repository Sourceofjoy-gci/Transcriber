import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { UsersPage } from "./UsersPage";
import { listMemberships, listRoles, listUsers } from "../lib/api";

vi.mock("../lib/api", () => ({
  ApiError: class ApiError extends Error {},
  createUser: vi.fn(),
  deleteUser: vi.fn(),
  listMemberships: vi.fn(),
  listRoles: vi.fn(),
  listUsers: vi.fn(),
  updateUser: vi.fn(),
}));

describe("UsersPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders memberships returned with backend field names", async () => {
    vi.mocked(listUsers).mockResolvedValue([
      {
        id: "user-1",
        email: "admin@example.com",
        display_name: "Admin User",
        is_active: true,
        last_login_at: null,
      },
    ]);
    vi.mocked(listRoles).mockResolvedValue([
      {
        id: "role-1",
        code: "organisation_administrator",
        name: "Organisation Administrator",
        permissions: ["users.manage"],
      },
    ]);
    vi.mocked(listMemberships).mockResolvedValue([
      {
        id: "membership-1",
        user_id: "user-1",
        organisation_id: "org-1",
        role_id: "role-1",
        role_code: "organisation_administrator",
        status: "active",
        created_at: "2026-07-06T00:00:00Z",
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
          <UsersPage />
        </QueryClientProvider>,
      );
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(container.textContent).toContain("Admin User");
    expect(container.textContent).toContain("Organisation Administrator");
    expect(container.textContent).toContain("Recent membership activity");

    await act(async () => {
      root.unmount();
    });
    container.remove();
  });
});
