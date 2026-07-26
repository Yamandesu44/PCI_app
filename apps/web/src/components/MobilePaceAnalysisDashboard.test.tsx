import type { PaceAnalysis, RaceDetail } from "@pci/api-client";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  MobilePaceAnalysisDashboard,
  MobilePaceResultRow,
} from "./MobilePaceAnalysisDashboard";

const race = {
  race_key: "2026071910020811",
  race_date: "2026-07-19",
  jyo_cd: "10",
  track_type: "芝",
  distance_m: 2000,
  field_size: 4,
  status: "result",
  weather: "晴",
  track_condition: "良",
  grade: "G3",
  race_class: "小倉記念",
} as RaceDetail;

const horses = Array.from({ length: 4 }, (_, index) => ({
  horse_no: index + 1,
  frame_no: index + 1,
  horse_name: `テスト馬${index + 1}`,
  finish_pos: index + 1,
  running_style: index === 0 ? "差し" : "先行",
  pci: 50 + index,
  agari_3f_s: 34.5 + index,
  is_pci3_contributor: index < 3,
}));

const analysis = {
  race_key: race.race_key,
  field_size: 4,
  sample_size: 4,
  rpci_actual: 49,
  pci3_actual: 52,
  formula_version: "test",
  reasons: [],
  horses,
  comment: {
    headline: "差し馬が力を発揮した流れでした。",
    body: ["後方から脚を伸ばした馬が上位に入りました。"],
    reasons: [],
    model_version: "test",
  },
} as unknown as PaceAnalysis;

describe("MobilePaceAnalysisDashboard", () => {
  it("初期表示を3タブのサマリーと上位3頭に絞る", () => {
    const markup = renderToStaticMarkup(
      <MobilePaceAnalysisDashboard race={race} analysis={analysis} />,
    );

    expect(markup).toContain('aria-label="確定後分析の表示切り替え"');
    expect(markup.match(/role="tab"/g)).toHaveLength(3);
    expect(markup).toContain("上位3頭");
    expect(markup.match(/data-mobile-pace-result/g)).toHaveLength(3);
    expect(markup).not.toContain("テスト馬4");
    expect(markup).not.toContain("算出の根拠");
    expect(markup).not.toMatch(/>49</);
    expect(markup).not.toMatch(/>52</);
  });

  it("各馬結果を横スクロール不要の二段行で表示する", () => {
    const markup = renderToStaticMarkup(
      <MobilePaceResultRow horse={horses[0]!} trackType={race.track_type} />,
    );

    expect(markup).toContain("テスト馬1");
    expect(markup).toContain("差し");
    expect(markup).toContain("34.5秒");
    expect(markup).toContain('aria-label="上位3着"');
    expect(markup).not.toMatch(/>50</);
    // 馬番バッジは隊列予想・展開予想側と同じ枠色（1枠→白地）を使う。
    expect(markup).toMatch(/h-9 min-w-9[^"]*bg-white[^"]*"[^>]*>\s*1\s*</);
  });
});
