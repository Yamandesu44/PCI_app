import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AppHeader } from "./AppHeader";

describe("AppHeader", () => {
  it("モバイルでも主要ナビゲーションの名前と操作領域を保つ", () => {
    const markup = renderToStaticMarkup(<AppHeader />);

    expect(markup).toContain('aria-label="メインナビゲーション"');
    expect(markup).toContain('aria-label="予想検証"');
    expect(markup).toContain('aria-label="レース一覧"');
    expect(markup.match(/h-11 w-11/g)).toHaveLength(2);
    expect(markup).toContain("focus-visible:ring-inset");
  });
});
