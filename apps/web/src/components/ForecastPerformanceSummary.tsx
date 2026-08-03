import Link from "next/link";
import {
  Activity,
  ChevronDown,
  Database,
  Minus,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import type {
  ForecastPerformance,
  ForecastPerformancePeriod,
} from "@pci/api-client";

import { ForecastConfidenceCalibration } from "@/components/ForecastConfidenceCalibration";
import { ForecastErrorPattern } from "@/components/ForecastErrorPattern";
import { ForecastEvaluationCoverage } from "@/components/ForecastEvaluationCoverage";
import { ForecastPerformanceTrendLazy } from "@/components/ForecastPerformanceTrendLazy";
import { ForecastRecentMisses } from "@/components/ForecastRecentMisses";
import { formatRaceDate } from "@/lib/races";

function rateLabel(rate: number | null | undefined): string {
  return rate == null ? "集計前" : `${Math.round(rate * 100)}%`;
}

function rateDelta(
  current: number | null | undefined,
  previous: number | null | undefined,
): number | null {
  return current == null || previous == null
    ? null
    : Math.round((current - previous) * 100);
}

function PeriodSelector({
  performance,
  selectedDate,
}: {
  performance: ForecastPerformance;
  selectedDate: string | null;
}) {
  const periods: ForecastPerformancePeriod[] = [30, 90, 180];

  function periodHref(days: ForecastPerformancePeriod): string {
    const params = new URLSearchParams({ performance_days: String(days) });
    if (selectedDate != null) params.set("date", selectedDate);
    return `/?${params.toString()}`;
  }

  return (
    <div className="flex flex-col items-start gap-2 lg:items-end">
      <nav
        className="inline-flex rounded-md border border-slate-200 bg-slate-50 p-0.5"
        aria-label="予想検証の集計期間"
      >
        {periods.map((days) => {
          const isSelected = performance.period_days === days;
          return (
            <Link
              key={days}
              href={periodHref(days)}
              aria-current={isSelected ? "page" : undefined}
              className={[
                "inline-flex min-h-11 items-center rounded px-3 text-xs font-semibold transition",
                isSelected
                  ? "bg-slate-950 text-white shadow-sm"
                  : "text-slate-600 hover:bg-white hover:text-slate-950",
              ].join(" ")}
            >
              {days}日
            </Link>
          );
        })}
      </nav>
      <p className="text-xs text-slate-500">
        {formatRaceDate(performance.date_from)} - {formatRaceDate(performance.date_to)}
      </p>
    </div>
  );
}

function PerformanceMetrics({
  performance,
}: {
  performance: ForecastPerformance;
}) {
  const groups = performance.groups.filter((group) =>
    ["overall", "turf", "dirt"].includes(group.key),
  );
  const hasWeeklyTrend = performance.weekly_trend.some(
    (point) => point.sample_size > 0,
  );

  return (
    <>
      <ForecastEvaluationCoverage
        eligibleRaceCount={performance.eligible_race_count}
        sampleSize={performance.sample_size}
        coverageRate={performance.coverage_rate}
      />

      {performance.sample_size > 0 ? (
        <>
          <dl className="mt-5 grid grid-cols-3 divide-x divide-slate-200 border-t border-slate-100 pt-4">
            {groups.map((group) => {
              const previous = performance.previous_period.groups.find(
                (candidate) => candidate.key === group.key,
              );
              const delta = rateDelta(group.hit_rate, previous?.hit_rate);
              const DeltaIcon = delta == null || delta === 0
                ? Minus
                : delta > 0
                  ? TrendingUp
                  : TrendingDown;
              const deltaTone = delta == null || delta === 0
                ? "text-slate-500"
                : delta > 0
                  ? "text-emerald-700"
                  : "text-amber-700";

              return (
                <div className="px-2 first:pl-0 sm:px-6 sm:first:pl-0" key={group.key}>
                  <dt className="text-xs font-medium text-slate-500">{group.label}</dt>
                  <dd className="mt-1 text-xl font-bold tabular-nums text-slate-950 sm:text-2xl">
                    {rateLabel(group.hit_rate)}
                  </dd>
                  <dd className="mt-1 text-[11px] text-slate-500 sm:text-xs">
                    {group.sample_size}レース
                  </dd>
                  <dd className={`mt-2 flex items-center gap-1 text-[11px] font-semibold sm:text-xs ${deltaTone}`}>
                    <DeltaIcon className="h-3.5 w-3.5 shrink-0" aria-hidden />
                    {delta == null
                      ? "比較なし"
                      : `前期比 ${delta > 0 ? "+" : delta === 0 ? "±" : ""}${delta}pt`}
                  </dd>
                  {previous && previous.sample_size > 0 ? (
                    <dd className="mt-0.5 hidden text-[11px] text-slate-400 sm:block">
                      前期 {rateLabel(previous.hit_rate)} / {previous.sample_size}レース
                    </dd>
                  ) : null}
                </div>
              );
            })}
          </dl>
          <div
            className={
              hasWeeklyTrend
                ? "grid gap-6 lg:grid-cols-[minmax(240px,0.7fr)_minmax(0,1.3fr)]"
                : ""
            }
          >
            <ForecastConfidenceCalibration
              groups={performance.confidence_groups}
              cohortGroups={performance.confidence_cohort_groups ?? []}
              reviewTarget={performance.confidence_review_target ?? 100}
              reviewReady={performance.confidence_review_ready}
            />
            {hasWeeklyTrend ? (
              <ForecastPerformanceTrendLazy points={performance.weekly_trend} />
            ) : null}
          </div>
          <ForecastErrorPattern rows={performance.pace_matrix} />
          <ForecastRecentMisses
            misses={performance.recent_misses}
            periodDays={performance.period_days}
          />
        </>
      ) : (
        <div className="mt-5 flex items-center gap-3 border-t border-slate-100 pt-4 text-sm text-slate-600">
          <Database className="h-4 w-4 text-slate-400" aria-hidden />
          確定前に保存された予想を蓄積中です。
        </div>
      )}
    </>
  );
}

/** 保存済みの事前予想を、内部PCI/RPCI値を出さずに集計表示する。 */
export function ForecastPerformanceSummary({
  performance,
  selectedDate,
}: {
  performance: ForecastPerformance;
  selectedDate: string | null;
}) {
  const overall = performance.groups.find((group) => group.key === "overall");
  const coverage = Math.max(
    0,
    Math.min(100, Math.round((performance.coverage_rate ?? 0) * 100)),
  );
  const reviewTarget = performance.confidence_review_target ?? 100;
  const confidenceCohorts = performance.confidence_cohort_groups ?? [];
  const turfConfidenceCount = confidenceCohorts.find(
    (group) => group.key === "turf",
  )?.sample_size ?? 0;
  const dirtConfidenceCount = confidenceCohorts.find(
    (group) => group.key === "dirt",
  )?.sample_size ?? 0;
  const confidenceReviewReady = performance.confidence_review_ready ?? (
    turfConfidenceCount >= reviewTarget && dirtConfidenceCount >= reviewTarget
  );
  const mobileConfidenceLabel = confidenceReviewReady
    ? "新しい読みやすさ指標は再評価可能です"
    : `新しい読みやすさ指標は、芝${turfConfidenceCount}件、目標${reviewTarget}件。ダート${dirtConfidenceCount}件、目標${reviewTarget}件です`;
  const mobilePerformanceLabel = performance.sample_size > 0
    ? `展開一致${rateLabel(overall?.hit_rate)}。検証${performance.sample_size}件。カバー率${coverage}%`
    : `事前予想を蓄積中です。検証${performance.sample_size}件。カバー率${coverage}%`;

  return (
    <>
      <details
        data-mobile-performance-summary
        className="group mb-4 border-y border-slate-200 bg-white md:hidden"
      >
        <summary
          aria-label={`${mobileConfidenceLabel}。${mobilePerformanceLabel}。予想検証の詳細を開く`}
          className="flex min-h-16 cursor-pointer list-none items-center gap-3 px-3 py-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-emerald-600 [&::-webkit-details-marker]:hidden"
        >
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-emerald-50 text-emerald-700">
            <Activity className="h-4 w-4" aria-hidden />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[10px] font-semibold text-emerald-700">
              {confidenceReviewReady
                ? "新指標 再評価可能"
                : `新指標 芝${turfConfidenceCount}/${reviewTarget} ダ${dirtConfidenceCount}/${reviewTarget}`}
            </span>
            <span className="mt-0.5 block truncate text-sm font-semibold text-slate-950">
              {performance.sample_size > 0
                ? `展開一致 ${rateLabel(overall?.hit_rate)}`
                : "事前予想を蓄積中"}
            </span>
          </span>
          <span className="shrink-0 text-right">
            <span className="block text-xs font-bold tabular-nums text-slate-800">
              検証 {performance.sample_size}件
            </span>
            <span className="mt-0.5 block text-[10px] text-slate-500">
              カバー {coverage}%
            </span>
          </span>
          <ChevronDown
            className="h-4 w-4 shrink-0 text-slate-400 transition-transform group-open:rotate-180"
            aria-hidden
          />
        </summary>
        <div className="border-t border-slate-100 px-4 pb-5 pt-4">
          <h2 className="sr-only">予想検証の詳細</h2>
          <p className="mb-3 text-xs leading-5 text-slate-600">
            事前の展開想定と実際の流れを比較しています。
          </p>
          <PeriodSelector performance={performance} selectedDate={selectedDate} />
          <PerformanceMetrics performance={performance} />
        </div>
      </details>

      <section className="mb-8 hidden border-y border-slate-200 bg-white px-4 py-5 sm:px-6 md:block">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="flex items-center gap-2 text-xs font-semibold uppercase text-emerald-700">
              <Activity className="h-4 w-4" aria-hidden />
              直近{performance.period_days}日の予想検証
            </p>
            <h2 className="mt-1 text-lg font-bold text-slate-950">
              事前の展開想定と実際の流れ
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              保存済みの事前予想について、展開区分の一致率と直前の同期間との差です。
            </p>
          </div>
          <PeriodSelector performance={performance} selectedDate={selectedDate} />
        </div>
        <PerformanceMetrics performance={performance} />
      </section>
    </>
  );
}
