import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { StoragePage } from "./StoragePage";
import { getStorageOverview, purgeExpiredStorage } from "../lib/api";

vi.mock("../lib/api", () => ({
  getStorageOverview: vi.fn(),
  purgeExpiredStorage: vi.fn(),
}));

describe("StoragePage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders storage usage and triggers retention purge", async () => {
    vi.mocked(getStorageOverview).mockResolvedValue({
      provider: "local_filesystem",
      healthy: true,
      storage_bytes: 4096,
      original_bytes: 3072,
      derivative_bytes: 1024,
      active_assets: 2,
      deleted_assets: 1,
      legal_hold_assets: 1,
      retention_days: 30,
    });
    vi.mocked(purgeExpiredStorage).mockResolvedValue({
      status: "completed",
      purged_assets: 1,
      deleted_objects: 2,
    });
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
          <StoragePage />
        </QueryClientProvider>,
      );
    });
    await flushPromises();

    expect(container.textContent).toContain("Storage");
    expect(container.textContent).toContain("4.0 KB");
    expect(container.textContent).toContain("local filesystem");
    expect(container.textContent).toContain("30 days");

    await act(async () => {
      buttonByText(container, "Purge expired").click();
    });
    await flushPromises();

    expect(purgeExpiredStorage).toHaveBeenCalledOnce();
    expect(container.textContent).toContain("1 asset purged");

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
