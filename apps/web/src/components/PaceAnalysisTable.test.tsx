import type { HorsePaceAnalysis } from "@pci/api-client";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { PaceAnalysisTable } from "./PaceAnalysisTable";

function horse(overrides: Partial<HorsePaceAnalysis> = {}): HorsePaceAnalysis {
  return {
    horse_no: 1,
    frame_no: 1,
    finish_pos: 1,
    horse_name: "テスト馬",
    running_style: "先行",
    pci: 50,
    agari_3f_s: 34.5,
    is_pci3_contributor: true,
    ...overrides,
  };
}

describe("PaceAnalysisTable", () => {
  it("馬番バッジを隊列予想・展開予想と同じ枠色で表示する", () => {
    const markup = renderToStaticMarkup(
      <PaceAnalysisTable horses={[horse({ horse_no: 16, frame_no: 8 })]} trackType="芝" />,
    );

    expect(markup).toMatch(/bg-pink-400[^"]*"[^>]*>\s*16\s*</);
  });

  it("枠順未確定（frame_no=0）の馬は色を付けず「登録」表示にする", () => {
    const markup = renderToStaticMarkup(
      <PaceAnalysisTable horses={[horse({ horse_no: 5, frame_no: 0 })]} trackType="芝" />,
    );

    expect(markup).toMatch(/bg-slate-100[^"]*"[^>]*>\s*登録\s*</);
  });

  it("ペース傾向はダート専用閾値で判定する（trackType未考慮だと誤判定になる回帰テスト）", () => {
    // pci=44はダートとしては平均域（40〜46）だが、芝の閾値（49未満でハイ）を
    // 誤って使うと「ハイ」と表示されてしまう。
    const markup = renderToStaticMarkup(
      <PaceAnalysisTable horses={[horse({ pci: 44 })]} trackType="ダート" />,
    );

    expect(markup).toContain(">平均<");
    expect(markup).not.toContain(">ハイ<");
  });
});
