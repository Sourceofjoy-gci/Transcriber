import { afterEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ReportTemplatesPage } from "./ReportTemplatesPage";
import {
  createReportTemplate,
  listReportTemplates,
  previewReportTemplate,
} from "../lib/api";

vi.mock("../lib/api", () => ({
  ApiError: class ApiError extends Error {},
  createReportTemplate: vi.fn(),
  deleteReportTemplate: vi.fn(),
  disableReportTemplate: vi.fn(),
  enableReportTemplate: vi.fn(),
  listReportTemplates: vi.fn(),
  previewReportTemplate: vi.fn(),
  updateReportTemplate: vi.fn(),
}));

describe("ReportTemplatesPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders templates, creates a schema-backed template, and previews it", async () => {
    vi.mocked(listReportTemplates).mockResolvedValue([
      {
        id: "template-1",
        kind: "meeting",
        name: "Meeting minutes",
        schema: { sections: ["Executive summary", "Action items"] },
        prompt_template: "Summarise the meeting.",
        enabled: true,
        is_builtin: true,
      },
    ]);
    vi.mocked(createReportTemplate).mockResolvedValue({
      id: "template-2",
      kind: "client_brief",
      name: "Client brief",
      schema: { sections: ["Overview", "Risks"] },
      prompt_template: null,
      enabled: true,
      is_builtin: false,
    });
    vi.mocked(previewReportTemplate).mockResolvedValue({
      content: {
        title: "Template preview",
        sections: [{ heading: "Overview", body: "Preview body" }],
      },
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
          <ReportTemplatesPage />
        </QueryClientProvider>,
      );
    });
    await flushPromises();

    expect(container.textContent).toContain("Meeting minutes");
    expect(container.textContent).toContain("Executive summary");

    await act(async () => {
      buttonByText(container, "New template").click();
    });
    setInput(container, "Template name", "Client brief");
    setInput(container, "Kind", "client_brief");
    setTextarea(container, "Sections", "Overview\nRisks");
    await act(async () => {
      buttonByText(container, "Create template").click();
    });
    expect(createReportTemplate).toHaveBeenCalledWith({
      name: "Client brief",
      kind: "client_brief",
      schema: { sections: ["Overview", "Risks"] },
      prompt_template: "",
    });

    setInput(container, "Preview transcript ID", "transcript-1");
    await act(async () => {
      buttonByText(container, "Preview").click();
    });
    expect(previewReportTemplate).toHaveBeenCalledWith("template-1", {
      transcript_id: "transcript-1",
      title: "Template preview",
    });
    await flushPromises();
    expect(container.textContent).toContain("Preview body");

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

function setInput(container: HTMLElement, label: string, value: string): void {
  const input = Array.from(
    container.querySelectorAll<HTMLInputElement>("input"),
  ).find((candidate) => candidate.getAttribute("aria-label") === label);
  if (!input) throw new Error(`Could not find input: ${label}`);
  act(() => {
    input.value = value;
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

function setTextarea(
  container: HTMLElement,
  label: string,
  value: string,
): void {
  const textarea = Array.from(
    container.querySelectorAll<HTMLTextAreaElement>("textarea"),
  ).find((candidate) => candidate.getAttribute("aria-label") === label);
  if (!textarea) throw new Error(`Could not find textarea: ${label}`);
  act(() => {
    textarea.value = value;
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

async function flushPromises(): Promise<void> {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}
