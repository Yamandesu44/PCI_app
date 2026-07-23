import type {
  ForecastMissQuery,
  ForecastPerformancePeriod,
} from "@pci/api-client";

export type ReviewTrack = "all" | "芝" | "ダート";
export type ReviewPace = "all" | "ハイ" | "平均" | "スロー";

export interface ForecastReviewFilters {
  days: ForecastPerformancePeriod;
  track: ReviewTrack;
  predicted: ReviewPace;
  actual: ReviewPace;
  page: number;
}

const PAGE_SIZE = 25;

export function parseForecastReviewFilters(params: {
  days?: string;
  track?: string;
  predicted?: string;
  actual?: string;
  page?: string;
}): ForecastReviewFilters {
  const days = params.days === "30" || params.days === "180"
    ? Number(params.days) as ForecastPerformancePeriod
    : 90;
  const track: ReviewTrack =
    params.track === "芝" || params.track === "ダート" ? params.track : "all";
  const predicted = parsePace(params.predicted);
  const actual = parsePace(params.actual);
  const parsedPage = Number(params.page);
  const page = Number.isInteger(parsedPage) && parsedPage > 0 ? parsedPage : 1;
  return { days, track, predicted, actual, page };
}

export function toForecastMissQuery(
  filters: ForecastReviewFilters,
): ForecastMissQuery {
  return {
    days: filters.days,
    trackType: filters.track === "all" ? undefined : filters.track,
    predictedLabel: filters.predicted === "all" ? undefined : filters.predicted,
    actualLabel: filters.actual === "all" ? undefined : filters.actual,
    offset: (filters.page - 1) * PAGE_SIZE,
    limit: PAGE_SIZE,
  };
}

export function forecastReviewHref(
  filters: ForecastReviewFilters,
  page: number,
): string {
  const params = new URLSearchParams({ days: String(filters.days) });
  if (filters.track !== "all") params.set("track", filters.track);
  if (filters.predicted !== "all") params.set("predicted", filters.predicted);
  if (filters.actual !== "all") params.set("actual", filters.actual);
  if (page > 1) params.set("page", String(page));
  return `/forecast-review?${params.toString()}`;
}

function parsePace(value: string | undefined): ReviewPace {
  return value === "ハイ" || value === "平均" || value === "スロー"
    ? value
    : "all";
}
