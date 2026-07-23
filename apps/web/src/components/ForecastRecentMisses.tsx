import Link from "next/link";
import { ArrowRight, ChevronDown } from "lucide-react";
import type { ForecastMiss } from "@pci/api-client";

import { formatRaceDate, jyoName, raceNumber } from "@/lib/races";

function raceLabel(miss: ForecastMiss): string {
  const raceClass = miss.race_class?.trim();
  return raceClass &&
    !raceClass.startsWith("@") &&
    !raceClass.startsWith("＠") &&
    !["...", "…", "-", "－"].includes(raceClass)
    ? raceClass
    : `${jyoName(miss.jyo_cd)} ${raceNumber(miss.race_key)}`;
}

/** 予想区分と実績区分が異なった直近レースを、回顧画面への導線付きで表示する。 */
export function ForecastRecentMisses({ misses }: { misses: ForecastMiss[] }) {
  if (misses.length === 0) return null;

  return (
    <details className="group mt-5 border-t border-slate-100 pt-5">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-left">
        <div>
          <h3 className="text-sm font-bold text-slate-900">直近の不一致レース</h3>
          <p className="mt-1 text-xs text-slate-500">
            実際の流れが想定と異なったレースを確認できます
          </p>
        </div>
        <ChevronDown
          className="h-4 w-4 shrink-0 text-slate-400 transition-transform group-open:rotate-180"
          aria-hidden
        />
      </summary>

      <div className="mt-3 divide-y divide-slate-100 border-y border-slate-100">
        {misses.map((miss) => (
          <Link
            className="grid gap-2 px-1 py-3 transition hover:bg-slate-50 sm:grid-cols-[minmax(0,1fr)_auto_auto] sm:items-center sm:gap-5 sm:px-3"
            href={`/races/${miss.race_key}/pace-analysis`}
            key={miss.race_key}
          >
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-slate-900">
                {raceLabel(miss)}
              </p>
              <p className="mt-0.5 text-xs text-slate-500">
                {formatRaceDate(miss.race_date)}・{jyoName(miss.jyo_cd)}{" "}
                {raceNumber(miss.race_key)}・{miss.track_type}{miss.distance_m}m
              </p>
            </div>
            <p className="text-xs text-slate-600">
              予想 <strong className="text-slate-900">{miss.predicted_label}</strong>
              <ArrowRight className="mx-1 inline h-3.5 w-3.5" aria-hidden />
              実際 <strong className="text-amber-700">{miss.actual_label}</strong>
            </p>
            <ArrowRight
              className="hidden h-4 w-4 text-slate-400 sm:block"
              aria-hidden
            />
          </Link>
        ))}
      </div>
    </details>
  );
}
