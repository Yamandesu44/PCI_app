import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { ForecastMiss } from "@pci/api-client";

import { ForecastRecentMisses } from "./ForecastRecentMisses";

describe("ForecastRecentMisses", () => {
  it("折りたたみと一覧導線に44px以上の操作領域を確保する", () => {
    const misses = [
      {
        race_key: "2026072501010111",
        race_date: "2026-07-25",
        jyo_cd: "01",
        race_class: "TVh賞",
        track_type: "芝",
        distance_m: 1200,
        predicted_label: "平均的な流れ",
        actual_label: "速い流れ",
      },
    ] as ForecastMiss[];

    const markup = renderToStaticMarkup(
      <ForecastRecentMisses misses={misses} periodDays={90} />,
    );

    expect(markup).toContain("直近の不一致レース");
    expect(markup).toContain("flex min-h-11 cursor-pointer");
    expect(markup).toContain("inline-flex min-h-11 items-center");
  });
});
