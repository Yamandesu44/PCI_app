import type { IntegratedEntry, IntegratedRanking } from "@pci/api-client";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { IntegratedRankingView } from "./IntegratedRankingView";

function entry(overrides: Partial<IntegratedEntry> = {}): IntegratedEntry {
  return {
    rank: 1,
    horse_no: 1,
    frame_no: 1,
    horse_name: "テスト馬",
    mark: "本命",
    ability_tier: "上位",
    fit_label: "合致",
    reasons: [],
    ...overrides,
  };
}

function ranking(entries: IntegratedEntry[]): IntegratedRanking {
  return { entries, reasons: [], model_version: "integrated-v1" };
}

describe("IntegratedRankingView", () => {
  it("上位5頭は常に表示し、6位以下は折りたたむ", () => {
    const entries = Array.from({ length: 8 }, (_, i) =>
      entry({ rank: i + 1, horse_no: i + 1, frame_no: (i % 8) + 1 }),
    );
    const markup = renderToStaticMarkup(<IntegratedRankingView ranking={ranking(entries)} />);

    expect(markup).toContain("統合順位予想");
    expect(markup).toContain("6位以下を表示（3頭）");
  });

  it("馬番バッジを隊列予想・展開予想と同じ枠色で表示する", () => {
    const markup = renderToStaticMarkup(
      <IntegratedRankingView ranking={ranking([entry({ horse_no: 16, frame_no: 8 })])} />,
    );

    expect(markup).toMatch(/bg-pink-400[^"]*"[^>]*>\s*16\s*</);
  });

  it("枠順未確定（frame_no=0）の馬は色を付けず「登録」表示にする", () => {
    const markup = renderToStaticMarkup(
      <IntegratedRankingView ranking={ranking([entry({ horse_no: 5, frame_no: 0 })])} />,
    );

    expect(markup).toMatch(/bg-slate-100[^"]*"[^>]*>\s*登録\s*</);
  });

  it("分類・能力・展開適性のタグを表示する", () => {
    const markup = renderToStaticMarkup(
      <IntegratedRankingView
        ranking={ranking([
          entry({ mark: "穴", ability_tier: "中位", fit_label: "合致" }),
        ])}
      />,
    );

    expect(markup).toContain("穴（妙味）");
    expect(markup).toContain("能力中位");
    expect(markup).toContain("展開が向く");
  });

  it("エントリーが無い場合は何も表示しない", () => {
    const markup = renderToStaticMarkup(<IntegratedRankingView ranking={ranking([])} />);
    expect(markup).toBe("");
  });
});
