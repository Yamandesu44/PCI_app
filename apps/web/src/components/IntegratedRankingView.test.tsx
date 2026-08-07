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
  it("展開が向く馬を見出しに置く", () => {
    const markup = renderToStaticMarkup(
      <IntegratedRankingView ranking={ranking([entry({})])} />,
    );

    expect(markup).toContain("この展開が向きそうな馬");
  });

  it("向く馬は馬番順に並べる", () => {
    // 能力順に並べると先頭が推奨に見える。それは実測で否定された使い方
    // （ADR-2026-08-04）なので、順位を含意しない並びにする。
    const markup = renderToStaticMarkup(
      <IntegratedRankingView
        ranking={ranking([
          entry({ rank: 1, horse_no: 9, horse_name: "能力上位の馬" }),
          entry({ rank: 2, horse_no: 3, horse_name: "馬番が若い馬" }),
        ])}
      />,
    );

    expect(markup.indexOf("馬番が若い馬")).toBeLessThan(
      markup.indexOf("能力上位の馬"),
    );
  });

  it("向く馬には順位を振らない", () => {
    const markup = renderToStaticMarkup(
      <IntegratedRankingView ranking={ranking([entry({})])} />,
    );

    expect(markup).not.toContain("番目");
  });

  it("能力の並びは畳んで補助に置く", () => {
    const markup = renderToStaticMarkup(
      <IntegratedRankingView
        ranking={ranking([
          entry({ rank: 1, horse_no: 1, fit_label: "合致" }),
          entry({ rank: 2, horse_no: 2, fit_label: "中立" }),
          entry({ rank: 3, horse_no: 3, fit_label: "不利" }),
        ])}
      />,
    );

    expect(markup).toContain("近走内容による能力の並びを見る（2頭）");
  });

  it("向く馬がいない場合はその旨を出し、能力の並びを開いておく", () => {
    const markup = renderToStaticMarkup(
      <IntegratedRankingView
        ranking={ranking([
          entry({ rank: 1, horse_no: 1, fit_label: "中立" }),
          entry({ rank: 2, horse_no: 2, fit_label: "不利" }),
        ])}
      />,
    );

    expect(markup).toContain("特に向くと言える馬がいません");
    expect(markup).toMatch(/<details[^>]*\sopen/);
  });

  it("自分の順位と単勝人気を比べる文言は出さない", () => {
    // 実測（1位馬の勝率20.2% 対 単勝人気1位36.9%）に忠実ではあったが、
    // 最初に目に入るのが自己否定という構成だった。限界は残しつつ、
    // 比較による打ち消しは畳んだ先へ移す（勝ち馬を当てる順位ではない、と述べる）。
    const markup = renderToStaticMarkup(
      <IntegratedRankingView
        ranking={ranking([entry({ rank: 1, horse_no: 1, fit_label: "中立" })])}
      />,
    );

    expect(markup).not.toContain("単勝人気");
    expect(markup).toContain("勝ち馬を当てるための順位ではありません");
  });

  it("推奨ではないことは明示し続ける", () => {
    const markup = renderToStaticMarkup(
      <IntegratedRankingView ranking={ranking([entry({})])} />,
    );

    expect(markup).toContain("買うべき馬の推奨ではありません");
  });

  it("買い目の印は表示しない", () => {
    const marks = ["本命", "対抗", "穴（妙味）", "人気でも注意"];
    const markup = renderToStaticMarkup(
      <IntegratedRankingView
        ranking={ranking([
          entry({ mark: "本命", ability_tier: "上位", fit_label: "合致" }),
          entry({
            rank: 2,
            horse_no: 2,
            mark: "穴",
            ability_tier: "中位",
            fit_label: "合致",
          }),
        ])}
      />,
    );

    for (const mark of marks) {
      expect(markup).not.toContain(mark);
    }
  });

  it("能力・展開適性のタグは表示する（事実の提示）", () => {
    const markup = renderToStaticMarkup(
      <IntegratedRankingView
        ranking={ranking([entry({ ability_tier: "中位", fit_label: "合致" })])}
      />,
    );

    expect(markup).toContain("能力中位");
    expect(markup).toContain("展開が向く");
  });

  it("馬番バッジを隊列予想・展開予想と同じ枠色で表示する", () => {
    const markup = renderToStaticMarkup(
      <IntegratedRankingView
        ranking={ranking([entry({ horse_no: 16, frame_no: 8 })])}
      />,
    );

    expect(markup).toMatch(/bg-pink-400[^"]*"[^>]*>\s*16\s*</);
  });

  it("枠順未確定（frame_no=0）の馬は色を付けず「登録」表示にする", () => {
    const markup = renderToStaticMarkup(
      <IntegratedRankingView
        ranking={ranking([entry({ horse_no: 5, frame_no: 0 })])}
      />,
    );

    expect(markup).toMatch(/bg-slate-100[^"]*"[^>]*>\s*登録\s*</);
  });

  it("エントリーが無い場合は何も表示しない", () => {
    const markup = renderToStaticMarkup(
      <IntegratedRankingView ranking={ranking([])} />,
    );
    expect(markup).toBe("");
  });
});
