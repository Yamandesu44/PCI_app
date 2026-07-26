"use client";

import { ArrowRight, Flag, Route } from "lucide-react";
import { useState } from "react";

import { frameColorClass } from "@/lib/pace";
import type { Formation, FormationHorse } from "@pci/api-client";

function horseName(horse: FormationHorse): string {
  return horse.horse_name ?? `${horse.horse_no}番`;
}

function confidenceClass(label: string): string {
  if (label === "高") return "bg-emerald-100 text-emerald-800";
  if (label === "標準") return "bg-blue-100 text-blue-800";
  return "bg-slate-100 text-slate-600";
}

/** スマホでは4ゾーンを同時表示し、選んだ馬の根拠だけを下部へ展開する。 */
export function MobileFormationBoard({ formation }: { formation: Formation }) {
  const [selectedHorseNo, setSelectedHorseNo] = useState<number | null>(null);
  const selectedHorse = formation.groups
    .flatMap((group) => group.horses)
    .find((horse) => horse.horse_no === selectedHorseNo);

  return (
    <div className="md:hidden">
      <div
        data-mobile-formation-board
        className="grid grid-cols-4 overflow-hidden rounded-md border border-slate-200 bg-white shadow-sm"
      >
        {formation.groups.map((group, groupIndex) => (
          <section
            key={group.key}
            aria-label={group.label}
            className="min-w-0 border-r border-slate-200 last:border-r-0"
          >
            <div
              className={`flex h-10 items-center justify-center gap-1 border-b border-slate-200 px-1 ${
                groupIndex === 0 ? "bg-emerald-50" : "bg-slate-50"
              }`}
            >
              {groupIndex === 0 ? (
                <Flag className="h-3.5 w-3.5 shrink-0 text-emerald-700" aria-hidden />
              ) : null}
              <h3 className="m-0 truncate text-[11px] font-semibold text-slate-800">
                {group.label}
              </h3>
            </div>

            {group.horses.length === 0 ? (
              <div className="flex h-14 items-center justify-center text-xs text-slate-300">
                —
              </div>
            ) : (
              <ul className="m-0 grid list-none gap-1.5 p-1.5">
                {group.horses.map((horse) => {
                  const isSelected = horse.horse_no === selectedHorseNo;
                  return (
                    <li key={horse.horse_no} className="min-w-0">
                      <button
                        type="button"
                        data-mobile-formation-horse
                        aria-label={`${horseName(horse)}の隊列詳細`}
                        aria-pressed={isSelected}
                        onClick={() =>
                          setSelectedHorseNo(isSelected ? null : horse.horse_no)
                        }
                        className={`flex min-h-12 w-full min-w-0 flex-col items-center justify-center gap-0.5 rounded border px-1 py-1 ${
                          isSelected
                            ? "border-slate-950 bg-slate-100 ring-1 ring-slate-950"
                            : "border-slate-200 bg-white"
                        }`}
                      >
                        <span
                          className={`flex h-6 min-w-6 items-center justify-center rounded border px-1 text-[10px] font-bold ${frameColorClass(horse.frame_no)}`}
                          aria-label={`${horse.frame_no}枠`}
                        >
                          {horse.horse_no}
                        </span>
                        <span className="block w-full truncate text-center text-[10px] font-semibold text-slate-700">
                          {horseName(horse)}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        ))}
      </div>

      {selectedHorse ? (
        <article
          data-mobile-formation-detail
          className="mt-2 rounded-md border border-slate-200 bg-white p-3 shadow-sm"
        >
          <div className="flex items-center gap-2.5">
            <span
              className={`flex h-8 min-w-8 shrink-0 items-center justify-center rounded border px-1 text-xs font-bold ${frameColorClass(selectedHorse.frame_no)}`}
              aria-label={`${selectedHorse.frame_no}枠`}
            >
              {selectedHorse.horse_no}
            </span>
            <div className="min-w-0 flex-1">
              <p className="m-0 truncate text-sm font-semibold text-slate-950">
                {horseName(selectedHorse)}
              </p>
              <p className="m-0 mt-0.5 text-xs text-slate-500">
                {selectedHorse.running_style}
              </p>
            </div>
            <span
              className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold ${confidenceClass(selectedHorse.confidence_label)}`}
            >
              信頼度 {selectedHorse.confidence_label}
            </span>
          </div>
          {selectedHorse.reasons[0] ? (
            <p className="m-0 mt-2 border-t border-slate-100 pt-2 text-xs leading-5 text-slate-600">
              {selectedHorse.reasons[0].description}
            </p>
          ) : null}
        </article>
      ) : null}
    </div>
  );
}

/** 枠順確定後の序盤隊列を、先頭から後方まで4ゾーンで表示する。 */
export function FormationView({ formation }: { formation: Formation }) {
  return (
    <section aria-labelledby="formation-heading">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2 md:mb-4 md:gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-md bg-blue-50 text-blue-700 md:h-8 md:w-8">
              <Route className="h-4 w-4" aria-hidden />
            </span>
            <h2
              id="formation-heading"
              className="m-0 text-base font-semibold tracking-normal text-slate-950 md:text-lg"
            >
              隊列予想
            </h2>
          </div>
          <p className="m-0 mt-1 text-xs text-slate-500 md:mt-2 md:text-sm">
            スタート後の想定ポジション
          </p>
        </div>
        <span className="rounded-md border border-emerald-200 bg-emerald-50 px-2 py-1 text-[10px] font-semibold text-emerald-700 md:px-2.5 md:text-xs">
          枠順確定後
        </span>
      </div>

      <div className="md:overflow-hidden md:rounded-lg md:border md:border-slate-200 md:bg-white md:shadow-sm">
        <MobileFormationBoard formation={formation} />

        <div className="hidden md:grid md:grid-cols-4">
          {formation.groups.map((group, groupIndex) => (
            <div
              key={group.key}
              className="w-[78vw] shrink-0 snap-start border-r border-slate-200 p-4 last:border-r-0 md:w-auto md:min-w-0"
            >
              <div className="mb-3 flex h-8 items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  {groupIndex === 0 ? (
                    <Flag className="h-4 w-4 text-emerald-700" aria-hidden />
                  ) : null}
                  <h3 className="m-0 text-sm font-semibold text-slate-950">{group.label}</h3>
                </div>
                {groupIndex < formation.groups.length - 1 ? (
                  <ArrowRight className="hidden h-4 w-4 text-slate-300 md:block" aria-hidden />
                ) : null}
              </div>

              {group.horses.length === 0 ? (
                <div className="flex min-h-24 items-center justify-center border-t border-dashed border-slate-200 text-xs text-slate-400">
                  該当馬なし
                </div>
              ) : (
                <ul className="m-0 grid list-none gap-2 p-0">
                  {group.horses.map((horse) => (
                    <li
                      key={horse.horse_no}
                      className="rounded-md border border-slate-200 bg-slate-50/80 p-3"
                    >
                      <div className="flex items-start gap-2.5">
                        <span
                          className={`flex h-8 w-8 shrink-0 items-center justify-center rounded border text-xs font-bold ${frameColorClass(horse.frame_no)}`}
                          aria-label={`${horse.frame_no}枠`}
                        >
                          {horse.horse_no}
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-start justify-between gap-2">
                            <p className="m-0 truncate text-sm font-semibold text-slate-950">
                              {horseName(horse)}
                            </p>
                            <span
                              className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold ${confidenceClass(horse.confidence_label)}`}
                            >
                              {horse.confidence_label}
                            </span>
                          </div>
                          <p className="m-0 mt-1 text-xs font-medium text-slate-500">
                            {horse.running_style}
                          </p>
                        </div>
                      </div>
                      {horse.reasons[0] ? (
                        <p className="m-0 mt-2 text-xs leading-5 text-slate-500">
                          {horse.reasons[0].description}
                        </p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
