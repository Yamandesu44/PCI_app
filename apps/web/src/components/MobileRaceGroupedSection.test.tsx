import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type {
  RaceBoardForecast,
  RaceSummary,
} from "@pci/api-client";

import {
  MobileRaceGroupedSection,
  type RaceDateItemGroup,
} from "./MobileRaceGroupedSection";

function race(
  raceKey: string,
  jyoCd: string,
  raceClass: string,
): RaceSummary {
  return {
    race_key: raceKey,
    race_date: "2026-07-25",
    jyo_cd: jyoCd,
    status: "entries",
    race_class: raceClass,
    grade: null,
    track_type: "芝",
    distance_m: 1800,
    field_size: 16,
  } as RaceSummary;
}

const forecast = {
  pace_label: "やや速い流れ",
  confidence: 0.72,
  top_fit_strength: "strong",
  top_fit_label: "向く",
  top_horse_no: 4,
} as RaceBoardForecast;

const dateGroups: RaceDateItemGroup[] = [
  {
    raceDate: "2026-07-25",
    venues: [
      {
        jyoCd: "04",
        venueName: "新潟",
        items: [
          { race: race("2026072504020101", "04", "2歳未勝利"), forecast },
          { race: race("2026072504020102", "04", "3歳未勝利"), forecast: null },
        ],
      },
      {
        jyoCd: "07",
        venueName: "中京",
        items: [
          { race: race("2026072507030101", "07", "2歳新馬"), forecast },
        ],
      },
      {
        jyoCd: "01",
        venueName: "札幌",
        items: [
          { race: race("2026072501010101", "01", "3歳未勝利"), forecast },
        ],
      },
    ],
  },
];

describe("MobileRaceGroupedSection", () => {
  it("最初の競馬場だけをコンパクトなレース行で表示する", () => {
    const markup = renderToStaticMarkup(
      <MobileRaceGroupedSection
        sectionId="weekend"
        dateGroups={dateGroups}
      />,
    );

    expect(markup.match(/data-mobile-venue-tab/g)).toHaveLength(3);
    expect(markup.match(/tabindex="0"/g)).toHaveLength(1);
    expect(markup.match(/tabindex="-1"/g)).toHaveLength(2);
    expect(markup).toContain("focus-visible:ring-inset");
    expect(markup).toContain("min-h-11 min-w-0 rounded");
    expect(markup).toContain("text-slate-600 hover:text-slate-900");
    expect(markup.match(/data-mobile-race-row/g)).toHaveLength(2);
    expect(markup).toContain('aria-selected="true"');
    expect(markup).toContain("2歳未勝利");
    expect(markup).not.toContain("2歳新馬");
    expect(markup).not.toContain("推奨理由");
  });

  it("タブとパネルをアクセシブルな関連付けで表示する", () => {
    const markup = renderToStaticMarkup(
      <MobileRaceGroupedSection
        sectionId="confirmed"
        dateGroups={dateGroups}
        featured
      />,
    );

    expect(markup).toContain('role="tablist"');
    expect(markup).toContain('role="tabpanel"');
    expect(markup).toContain(
      'aria-controls="confirmed-2026-07-25-panel"',
    );
    expect(markup).toContain(
      'aria-labelledby="confirmed-2026-07-25-tab-04"',
    );
  });
});
