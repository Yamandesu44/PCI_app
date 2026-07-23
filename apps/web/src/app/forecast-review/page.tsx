import Link from "next/link";
import { redirect } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  BarChart3,
  CalendarRange,
  ChevronLeft,
  ChevronRight,
  ListFilter,
} from "lucide-react";
import type { ForecastMisses } from "@pci/api-client";

import { api } from "@/lib/api";
import {
  forecastReviewHref,
  parseForecastReviewFilters,
  toForecastMissQuery,
  type ReviewPace,
  type ReviewTrack,
} from "@/lib/forecastReview";
import {
  formatRaceDate,
  jyoName,
  raceNameOrFallback,
  raceNumber,
} from "@/lib/races";

export const dynamic = "force-dynamic";

interface PageProps {
  searchParams?: Promise<{
    days?: string;
    track?: string;
    predicted?: string;
    actual?: string;
    page?: string;
  }>;
}

const TRACK_OPTIONS: Array<{ value: ReviewTrack; label: string }> = [
  { value: "all", label: "芝・ダート" },
  { value: "芝", label: "芝" },
  { value: "ダート", label: "ダート" },
];
const PACE_OPTIONS: Array<{ value: ReviewPace; label: string }> = [
  { value: "all", label: "すべて" },
  { value: "ハイ", label: "速い流れ" },
  { value: "平均", label: "平均的な流れ" },
  { value: "スロー", label: "落ち着いた流れ" },
];

export default async function ForecastReviewPage({ searchParams }: PageProps) {
  const filters = parseForecastReviewFilters((await searchParams) ?? {});
  let result: ForecastMisses | null = null;
  try {
    result = await api.getForecastMisses(toForecastMissQuery(filters));
  } catch {
    result = null;
  }

  const totalPages = result == null
    ? 1
    : Math.max(1, Math.ceil(result.total_count / result.limit));
  if (result != null && filters.page > totalPages) {
    redirect(forecastReviewHref(filters, totalPages));
  }
  const currentPage = Math.min(filters.page, totalPages);
  const hasPrevious = currentPage > 1;
  const hasNext = result != null && currentPage < totalPages;

  return (
    <main className="mx-auto w-full max-w-7xl px-4 py-7 sm:px-6 lg:px-8 lg:py-10">
      <Link
        href={`/?performance_days=${filters.days}`}
        className="inline-flex items-center gap-2 text-sm font-semibold text-slate-600 transition hover:text-slate-950"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden />
        レースボード
      </Link>

      <header className="mt-6 flex flex-col gap-4 border-b border-slate-200 pb-6 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="flex items-center gap-2 text-xs font-semibold uppercase text-emerald-700">
            <BarChart3 className="h-4 w-4" aria-hidden />
            Forecast review
          </p>
          <h1 className="mt-2 text-2xl font-bold text-slate-950 sm:text-3xl">
            予想と異なったレース
          </h1>
          <p className="mt-2 text-sm text-slate-600">
            展開区分の不一致を開催条件別に確認します。
          </p>
        </div>
        {result ? (
          <div className="flex items-center gap-3 text-sm text-slate-600">
            <CalendarRange className="h-4 w-4 text-slate-400" aria-hidden />
            <span>
              {formatRaceDate(result.date_from)} - {formatRaceDate(result.date_to)}
            </span>
            <strong className="tabular-nums text-slate-950">{result.total_count}件</strong>
          </div>
        ) : null}
      </header>

      <section className="border-b border-slate-200 bg-white py-5">
        <form
          action="/forecast-review"
          className="grid gap-4 sm:grid-cols-2 lg:grid-cols-[repeat(4,minmax(0,1fr))_auto]"
          method="get"
        >
          <FilterSelect
            label="期間"
            name="days"
            value={String(filters.days)}
            options={[
              { value: "30", label: "直近30日" },
              { value: "90", label: "直近90日" },
              { value: "180", label: "直近180日" },
            ]}
          />
          <FilterSelect
            label="コース"
            name="track"
            value={filters.track}
            options={TRACK_OPTIONS}
          />
          <FilterSelect
            label="予想"
            name="predicted"
            value={filters.predicted}
            options={PACE_OPTIONS}
          />
          <FilterSelect
            label="実際"
            name="actual"
            value={filters.actual}
            options={PACE_OPTIONS}
          />
          <button
            className="inline-flex h-10 items-center justify-center gap-2 self-end rounded-md bg-slate-950 px-4 text-sm font-semibold text-white transition hover:bg-emerald-700"
            type="submit"
          >
            <ListFilter className="h-4 w-4" aria-hidden />
            絞り込む
          </button>
        </form>
      </section>

      {result == null ? (
        <section className="py-12 text-sm text-slate-600">
          予想検証データを取得できませんでした。APIの起動状態を確認してください。
        </section>
      ) : result.items.length === 0 ? (
        <section className="py-12 text-center">
          <p className="text-sm font-semibold text-slate-800">
            条件に一致する不一致レースはありません。
          </p>
          <Link
            className="mt-3 inline-flex text-sm font-semibold text-emerald-700"
            href={`/forecast-review?days=${filters.days}`}
          >
            絞り込みを解除
          </Link>
        </section>
      ) : (
        <section className="divide-y divide-slate-200" aria-label="不一致レース一覧">
          {result.items.map((miss) => (
            <Link
              className="grid gap-3 py-5 transition hover:bg-white sm:grid-cols-[92px_minmax(0,1fr)_auto_auto] sm:items-center sm:px-3"
              href={`/races/${miss.race_key}/pace-analysis`}
              key={miss.race_key}
            >
              <div>
                <p className="text-xs font-semibold text-slate-500">
                  {formatRaceDate(miss.race_date)}
                </p>
                <p className="mt-1 text-sm font-bold text-slate-900">
                  {jyoName(miss.jyo_cd)} {raceNumber(miss.race_key)}
                </p>
              </div>
              <div className="min-w-0">
                <h2 className="truncate text-sm font-bold text-slate-950">
                  {raceNameOrFallback(miss)}
                </h2>
                <p className="mt-1 text-xs text-slate-500">
                  {miss.track_type}{miss.distance_m}m
                </p>
              </div>
              <div className="flex items-center gap-2 text-xs">
                <span className="rounded bg-slate-100 px-2 py-1 font-semibold text-slate-700">
                  予想 {miss.predicted_label}
                </span>
                <ArrowRight className="h-3.5 w-3.5 text-slate-400" aria-hidden />
                <span className="rounded bg-amber-50 px-2 py-1 font-semibold text-amber-800">
                  実際 {miss.actual_label}
                </span>
              </div>
              <ChevronRight className="hidden h-4 w-4 text-slate-400 sm:block" aria-hidden />
            </Link>
          ))}
        </section>
      )}

      {result != null && result.total_count > result.limit ? (
        <nav
          className="flex items-center justify-between border-t border-slate-200 pt-5"
          aria-label="不一致レースのページ切り替え"
        >
          {hasPrevious ? (
            <Link
              className="inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-white"
              href={forecastReviewHref(filters, currentPage - 1)}
            >
              <ChevronLeft className="h-4 w-4" aria-hidden />
              前へ
            </Link>
          ) : <span />}
          <span className="text-xs font-semibold tabular-nums text-slate-500">
            {currentPage} / {totalPages}
          </span>
          {hasNext ? (
            <Link
              className="inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-white"
              href={forecastReviewHref(filters, currentPage + 1)}
            >
              次へ
              <ChevronRight className="h-4 w-4" aria-hidden />
            </Link>
          ) : <span />}
        </nav>
      ) : null}
    </main>
  );
}

function FilterSelect({
  label,
  name,
  value,
  options,
}: {
  label: string;
  name: string;
  value: string;
  options: Array<{ value: string; label: string }>;
}) {
  return (
    <label className="grid gap-1.5 text-xs font-semibold text-slate-600">
      {label}
      <select
        className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm font-medium text-slate-900 outline-none transition focus:border-emerald-600"
        defaultValue={value}
        name={name}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
