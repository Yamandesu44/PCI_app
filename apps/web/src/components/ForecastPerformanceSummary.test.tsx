import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { ForecastPerformance } from "@pci/api-client";

import { ForecastPerformanceSummary } from "./ForecastPerformanceSummary";

const performance = {
  period_days: 90,
  date_from: "2026-04-28",
  date_to: "2026-07-26",
  eligible_race_count: 120,
  sample_size: 48,
  coverage_rate: 0.4,
  confidence_review_target: 100,
  confidence_review_ready: false,
  groups: [
    { key: "overall", label: "全体", hit_rate: 0.625, sample_size: 48 },
    { key: "turf", label: "芝", hit_rate: 0.6, sample_size: 30 },
    { key: "dirt", label: "ダート", hit_rate: 0.667, sample_size: 18 },
  ],
  previous_period: { groups: [] },
  weekly_trend: [],
  confidence_groups: [
    { key: "strong", label: "読みやすい", hit_rate: 0.7, sample_size: 10 },
  ],
  confidence_cohort_groups: [
    { key: "overall", label: "全体", hit_rate: 0.7, sample_size: 18 },
    { key: "turf", label: "芝", hit_rate: 0.7, sample_size: 11 },
    { key: "dirt", label: "ダート", hit_rate: 0.7, sample_size: 7 },
  ],
  pace_matrix: [],
  recent_misses: [],
} as unknown as ForecastPerformance;

describe("ForecastPerformanceSummary", () => {
  it("スマホでは閉じたサマリーから検証状況を把握できる", () => {
    const markup = renderToStaticMarkup(
      <ForecastPerformanceSummary
        performance={performance}
        selectedDate="2026-07-25"
      />,
    );

    expect(markup).toContain("data-mobile-performance-summary");
    expect(markup).toContain("<summary");
    expect(markup).not.toContain("<details open");
    expect(markup).toContain("展開一致 63%");
    expect(markup).toContain("検証 48件");
    expect(markup).toContain("カバー 40%");
    expect(markup).toContain('<h2 class="sr-only">予想検証の詳細</h2>');
  });

  it("期間切替と詳細指標を折りたたみ内にも維持する", () => {
    const markup = renderToStaticMarkup(
      <ForecastPerformanceSummary
        performance={performance}
        selectedDate="2026-07-25"
      />,
    );

    expect(markup).toContain(
      'href="/?performance_days=30&amp;date=2026-07-25"',
    );
    expect(markup).toContain("inline-flex min-h-11 items-center");
    expect(markup).toContain("事前予想の検証カバー率");
    expect(markup).toContain("全体");
    expect(markup).toContain("新しい読みやすさ指標で保存された予想のみを集計");
    expect(markup).toContain("芝 11/100");
    expect(markup).toContain("ダート 7/100");
    expect(markup).toContain("残り 芝89件・ダート93件");
    expect(markup).not.toContain("RPCI");
  });

  it("旧API応答でコース別件数がなくても表示を継続する", () => {
    const {
      confidence_cohort_groups: _unusedGroups,
      confidence_review_target: _unusedTarget,
      confidence_review_ready: _unusedReady,
      ...legacyPerformance
    } = performance;
    const markup = renderToStaticMarkup(
      <ForecastPerformanceSummary
        performance={legacyPerformance as ForecastPerformance}
        selectedDate="2026-07-25"
      />,
    );

    expect(markup).toContain("芝 0/100");
    expect(markup).toContain("ダート 0/100");
  });

  it("芝とダートが目標へ達したら再評価可能と表示する", () => {
    const readyPerformance = {
      ...performance,
      confidence_review_ready: true,
      confidence_cohort_groups: [
        { key: "overall", label: "全体", hit_rate: 0.7, sample_size: 205 },
        { key: "turf", label: "芝", hit_rate: 0.7, sample_size: 105 },
        { key: "dirt", label: "ダート", hit_rate: 0.7, sample_size: 100 },
      ],
    } as unknown as ForecastPerformance;
    const markup = renderToStaticMarkup(
      <ForecastPerformanceSummary
        performance={readyPerformance}
        selectedDate="2026-07-25"
      />,
    );

    expect(markup).toContain("再評価可能");
    expect(markup).not.toContain("残り 芝");
  });
});
