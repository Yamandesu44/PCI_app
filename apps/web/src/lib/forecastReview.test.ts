import { describe, expect, it } from "vitest";

import {
  forecastReviewHref,
  parseForecastReviewFilters,
  toForecastMissQuery,
} from "./forecastReview";

describe("parseForecastReviewFilters", () => {
  it("対応するURL条件を型付きフィルターへ変換する", () => {
    expect(
      parseForecastReviewFilters({
        days: "30",
        track: "芝",
        predicted: "平均",
        actual: "ハイ",
        page: "2",
      }),
    ).toEqual({
      days: 30,
      track: "芝",
      predicted: "平均",
      actual: "ハイ",
      page: 2,
    });
  });

  it("不正値を既定値へ戻す", () => {
    expect(
      parseForecastReviewFilters({
        days: "60",
        track: "障害",
        predicted: "超ハイ",
        page: "-2",
      }),
    ).toEqual({
      days: 90,
      track: "all",
      predicted: "all",
      actual: "all",
      page: 1,
    });
  });
});

describe("toForecastMissQuery", () => {
  it("allを省略し、ページをoffsetへ変換する", () => {
    expect(
      toForecastMissQuery({
        days: 180,
        track: "ダート",
        predicted: "all",
        actual: "スロー",
        page: 3,
      }),
    ).toEqual({
      days: 180,
      trackType: "ダート",
      predictedLabel: undefined,
      actualLabel: "スロー",
      offset: 50,
      limit: 25,
    });
  });
});

describe("forecastReviewHref", () => {
  it("選択条件を維持してページリンクを作る", () => {
    const href = forecastReviewHref(
      {
        days: 30,
        track: "芝",
        predicted: "平均",
        actual: "ハイ",
        page: 1,
      },
      2,
    );

    expect(decodeURIComponent(href)).toBe(
      "/forecast-review?days=30&track=芝&predicted=平均&actual=ハイ&page=2",
    );
  });
});
