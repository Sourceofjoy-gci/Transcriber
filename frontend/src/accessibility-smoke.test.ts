import { describe, expect, it } from "vitest";

import appSource from "./App.tsx?raw";

describe("accessibility smoke checks", () => {
  it("names the primary navigation landmark", () => {
    expect(appSource).toContain('aria-label="Primary navigation"');
  });
});
