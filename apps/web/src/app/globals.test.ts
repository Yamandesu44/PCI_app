import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

describe("グローバルスタイル", () => {
  it("動きを減らすOS設定ではスクロールとアニメーションを抑制する", () => {
    const css = readFileSync(new URL("./globals.css", import.meta.url), "utf8");

    expect(css).toContain("@media (prefers-reduced-motion: reduce)");
    expect(css).toContain("scroll-behavior: auto");
    expect(css).toContain("animation-duration: 0.01ms");
    expect(css).toContain("transition-duration: 0.01ms");
  });
});
