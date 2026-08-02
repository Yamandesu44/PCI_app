import type { HorseFit } from "@pci/api-client";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { HorseFitTable } from "./HorseFitTable";

function horse(overrides: Partial<HorseFit> = {}): HorseFit {
  return {
    horse_no: 1,
    frame_no: 1,
    horse_name: "テスト馬",
    running_style: "先行",
    fit_label: "合致",
    pai: 70,
    reasons: [],
    ...overrides,
  };
}

describe("HorseFitTable", () => {
  it("馬番バッジを隊列予想と同じ枠色で表示する（馬番のみ・「馬番」ラベルは付けない）", () => {
    const markup = renderToStaticMarkup(
      <HorseFitTable horses={[horse({ horse_no: 16, frame_no: 8 })]} />,
    );

    expect(markup).toMatch(/bg-pink-400[^"]*"[^>]*>\s*16\s*</);
    expect(markup).not.toContain("馬番 16");
    expect(markup).toContain('aria-label="8枠"');
  });

  it("枠順未確定（frame_no=0）の馬は色を付けず「登録」表示にする", () => {
    const markup = renderToStaticMarkup(
      <HorseFitTable horses={[horse({ horse_no: 5, frame_no: 0 })]} />,
    );

    expect(markup).toMatch(/bg-slate-100[^"]*"[^>]*>\s*登録\s*</);
    expect(markup).toContain("登録順 5（馬番未確定）");
  });
});
