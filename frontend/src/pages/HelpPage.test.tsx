import React from "react";
import { describe, expect, it } from "vitest";
import { act } from "react";
import { createRoot } from "react-dom/client";

import { HelpPage } from "./HelpPage";

describe("HelpPage", () => {
  it("renders operator and user troubleshooting content", async () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);

    await act(async () => root.render(<HelpPage />));

    expect(container.textContent).toContain("Help");
    expect(container.textContent).toContain("Upload troubleshooting");
    expect(container.textContent).toContain("Worker operations");

    await act(async () => root.unmount());
    container.remove();
  });
});
