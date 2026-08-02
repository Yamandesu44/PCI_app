import type { Forecast, RaceDetail } from "@pci/api-client";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  MobileExpandableHorseRow,
  MobileRaceForecastDashboard,
} from "./MobileRaceForecastDashboard";

const race = {
  race_key: "2026072504020111",
  race_date: "2026-07-25",
  jyo_cd: "04",
  track_type: "芝",
  distance_m: 1000,
  field_size: 5,
  status: "upcoming",
} as RaceDetail;

const forecast = {
  pace_label: "やや速い流れ",
  scenario_headline: "前が競り合い、差し馬にも出番があります。",
  scenario_detail: "詳細",
  confidence: 0.72,
  predicted_rpci: 49,
  model_version: "test",
  forecast_reasons: [],
  front_runners: [],
  horses: Array.from({ length: 5 }, (_, index) => ({
    horse_no: index + 1,
    frame_no: index + 1,
    horse_name: `テスト馬${index + 1}`,
    running_style: index < 2 ? "先行" : "差し",
    pai: 90 - index * 5,
    fit_label: index === 4 ? "不利" : "向く",
    reasons: [],
  })),
  comment: {
    headline: "差し馬にも流れが向きそうです。",
    body: [],
    reasons: [],
    model_version: "test",
  },
} as unknown as Forecast;

describe("MobileRaceForecastDashboard", () => {
  it("初期表示を4タブのサマリーと恩恵馬TOP3に絞る", () => {
    const markup = renderToStaticMarkup(
      <MobileRaceForecastDashboard race={race} forecast={forecast} />,
    );

    expect(markup).toContain('role="tablist"');
    expect(markup.match(/role="tab"/g)).toHaveLength(4);
    expect(markup.match(/tabindex="0"/g)).toHaveLength(1);
    expect(markup.match(/tabindex="-1"/g)).toHaveLength(3);
    expect(markup).toContain("展開恩恵馬 TOP3");
    expect(markup.match(/data-mobile-benefit/g)).toHaveLength(3);
    expect(markup).not.toContain("テスト馬4");
    expect(markup).not.toContain("判断根拠データ");
    // 馬番バッジは隊列予想と同じ枠色（frame_no=1→白地、2→黒地）を使う。
    expect(markup).toMatch(/h-9 min-w-9[^"]*bg-white[^"]*"[^>]*>\s*1\s*</);
    expect(markup).toMatch(/h-9 min-w-9[^"]*bg-slate-950[^"]*"[^>]*>\s*2\s*</);
  });

  it("注目馬の理由を初期状態で閉じたコンパクト行にする", () => {
    const horse = forecast.horses?.[0];
    expect(horse).toBeDefined();

    const markup = renderToStaticMarkup(
      <MobileExpandableHorseRow
        horse={horse!}
        rank={1}
        label="軸候補"
        reason="今回の流れが向きそうです。"
        tone="benefit"
      />,
    );

    expect(markup).toContain("<details");
    expect(markup).not.toContain("<details open");
    expect(markup).toContain("<summary");
    expect(markup).toContain("今回の評価理由");
    expect(markup).toContain("今回の流れが向きそうです。");
    expect(markup).toContain("data-mobile-expandable-horse");
    // 1枠（frame_no=1）は隊列予想と同じ白地バッジになる。
    expect(markup).toMatch(/h-9 min-w-9[^"]*bg-white[^"]*"[^>]*>\s*1\s*</);
  });

  it("枠順未確定（frame_no=0）の馬は色を付けず「登録」表示にする", () => {
    const unassigned = { ...forecast.horses![0], frame_no: 0 };

    const markup = renderToStaticMarkup(
      <MobileExpandableHorseRow
        horse={unassigned}
        rank={1}
        label="軸候補"
        reason="今回の流れが向きそうです。"
        tone="benefit"
      />,
    );

    expect(markup).toContain("登録<");
    // 枠色を付けず、中立（slate-100）のバッジになる。
    expect(markup).toContain("bg-slate-100");
  });
});
