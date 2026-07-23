import Link from "next/link";
import { Activity, Database, Minus, TrendingDown, TrendingUp } from "lucide-react";
import type {
  ForecastPerformance,
  ForecastPerformancePeriod,
} from "@pci/api-client";

import { ForecastConfidenceCalibration } from "@/components/ForecastConfidenceCalibration";
import { ForecastErrorPattern } from "@/components/ForecastErrorPattern";
import { ForecastEvaluationCoverage } from "@/components/ForecastEvaluationCoverage";
import { ForecastPerformanceTrendLazy } from "@/components/ForecastPerformanceTrendLazy";
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

/** 保存済みの事前予想を、内部PCI/RPCI値を出さずに集計表示する。 */
export function ForecastPerformanceSummary({
  performance,
  selectedDate,
}: {
  performance: ForecastPerformance;
  selectedDate: string | null;
}) {
  const groups = performance.groups.filter((group) =>
    ["overall", "turf", "dirt"].includes(group.key),
  );
  const hasWeeklyTrend = performance.weekly_trend.some(
    (point) => point.sample_size > 0,
  );
  const periods: ForecastPerformancePeriod[] = [30, 90, 180];

  function periodHref(days: ForecastPerformancePeriod): string {
    const params = new URLSearchParams({ performance_days: String(days) });
    if (selectedDate != null) params.set("date", selectedDate);
    return `/?${params.toString()}`;
  }

  return (
    <section className="mb-8 border-y border-slate-200 bg-white px-4 py-5 sm:px-6">
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
                    "rounded px-3 py-1.5 text-xs font-semibold transition",
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
      </div>

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
                <div className="px-3 first:pl-0 sm:px-6 sm:first:pl-0" key={group.key}>
                  <dt className="text-xs font-medium text-slate-500">{group.label}</dt>
                  <dd className="mt-1 text-2xl font-bold tabular-nums text-slate-950">
                    {rateLabel(group.hit_rate)}
                  </dd>
                  <dd className="mt-1 text-xs text-slate-500">
                    {group.sample_size}レースを検証
                  </dd>
                  <dd className={`mt-2 flex items-center gap-1 text-xs font-semibold ${deltaTone}`}>
                    <DeltaIcon className="h-3.5 w-3.5 shrink-0" aria-hidden />
                    {delta == null
                      ? "前期比較なし"
                      : `前期比 ${delta > 0 ? "+" : delta === 0 ? "±" : ""}${delta}pt`}
                  </dd>
                  {previous && previous.sample_size > 0 ? (
                    <dd className="mt-0.5 text-[11px] text-slate-400">
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
            <ForecastConfidenceCalibration groups={performance.confidence_groups} />
            {hasWeeklyTrend ? (
              <ForecastPerformanceTrendLazy points={performance.weekly_trend} />
            ) : null}
          </div>
          <ForecastErrorPattern rows={performance.pace_matrix} />
        </>
      ) : (
        <div className="mt-5 flex items-center gap-3 border-t border-slate-100 pt-4 text-sm text-slate-600">
          <Database className="h-4 w-4 text-slate-400" aria-hidden />
          確定前に保存された予想を蓄積中です。
        </div>
      )}
    </section>
  );
}
