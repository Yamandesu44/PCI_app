import { Activity, Database } from "lucide-react";
import type { ForecastPerformance } from "@pci/api-client";

import { formatRaceDate } from "@/lib/races";

function rateLabel(rate: number | null | undefined): string {
  return rate == null ? "集計前" : `${Math.round(rate * 100)}%`;
}

/** 保存済みの事前予想を、内部PCI/RPCI値を出さずに集計表示する。 */
export function ForecastPerformanceSummary({
  performance,
}: {
  performance: ForecastPerformance;
}) {
  const groups = performance.groups.filter((group) =>
    ["overall", "turf", "dirt"].includes(group.key),
  );

  return (
    <section className="mb-8 border-y border-slate-200 bg-white py-5">
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
            保存済みの事前予想について、展開区分が一致した割合です。
          </p>
        </div>
        <p className="text-xs text-slate-500">
          {formatRaceDate(performance.date_from)} - {formatRaceDate(performance.date_to)}
        </p>
      </div>

      {performance.sample_size > 0 ? (
        <dl className="mt-5 grid grid-cols-3 divide-x divide-slate-200 border-t border-slate-100 pt-4">
          {groups.map((group) => (
            <div className="px-3 first:pl-0 sm:px-6 sm:first:pl-0" key={group.key}>
              <dt className="text-xs font-medium text-slate-500">{group.label}</dt>
              <dd className="mt-1 text-2xl font-bold tabular-nums text-slate-950">
                {rateLabel(group.hit_rate)}
              </dd>
              <dd className="mt-1 text-xs text-slate-500">
                {group.sample_size}レースを検証
              </dd>
            </div>
          ))}
        </dl>
      ) : (
        <div className="mt-5 flex items-center gap-3 border-t border-slate-100 pt-4 text-sm text-slate-600">
          <Database className="h-4 w-4 text-slate-400" aria-hidden />
          確定前に保存された予想を蓄積中です。
        </div>
      )}
    </section>
  );
}
