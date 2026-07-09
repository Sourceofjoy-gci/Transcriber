import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { OrganisationsPage } from "./OrganisationsPage";
import {
  createOrganisation,
  listOrganisations,
  setActiveOrganisationId,
  updateOrganisation,
} from "../lib/api";

vi.mock("../lib/api", () => ({
  ApiError: class ApiError extends Error {},
  createOrganisation: vi.fn(),
  listOrganisations: vi.fn(),
  setActiveOrganisationId: vi.fn(),
  updateOrganisation: vi.fn(),
}));

describe("OrganisationsPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders organisation switcher and management controls", async () => {
    vi.mocked(listOrganisations).mockResolvedValue([
      {
        id: "org-1",
        name: "Local Organisation",
        slug: "local-organisation",
        external_apis_allowed: true,
        local_only_enforced: false,
        retention_days: 30,
        role_code: "system_administrator",
        is_current: true,
      },
    ]);
    vi.mocked(createOrganisation).mockResolvedValue({} as never);
    vi.mocked(updateOrganisation).mockResolvedValue({} as never);

    const { container, root } = await renderPage(<OrganisationsPage />);

    expect(container.textContent).toContain("Organisations");
    expect(container.textContent).toContain("Local Organisation");
    await act(async () => buttonByText(container, "Switch").click());
    expect(setActiveOrganisationId).toHaveBeenCalledWith("org-1");
    await act(async () =>
      buttonByText(container, "Create organisation").click(),
    );
    expect(createOrganisation).toHaveBeenCalled();

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
