import { ArrowRight, Flag, Route } from "lucide-react";

import type { Formation, FormationHorse } from "@pci/api-client";

const FRAME_CLASS: Record<number, string> = {
  1: "border-slate-300 bg-white text-slate-950",
  2: "border-slate-950 bg-slate-950 text-white",
  3: "border-red-600 bg-red-600 text-white",
  4: "border-blue-600 bg-blue-600 text-white",
  5: "border-yellow-400 bg-yellow-400 text-slate-950",
  6: "border-green-600 bg-green-600 text-white",
  7: "border-orange-500 bg-orange-500 text-white",
  8: "border-pink-400 bg-pink-400 text-slate-950",
};

function horseName(horse: FormationHorse): string {
  return horse.horse_name ?? `${horse.horse_no}番`;
}

function confidenceClass(label: string): string {
  if (label === "高") return "bg-emerald-100 text-emerald-800";
  if (label === "標準") return "bg-blue-100 text-blue-800";
  return "bg-slate-100 text-slate-600";
}

/** 枠順確定後の序盤隊列を、先頭から後方まで4ゾーンで表示する。 */
export function FormationView({ formation }: { formation: Formation }) {
  return (
    <section aria-labelledby="formation-heading">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-md bg-blue-50 text-blue-700">
              <Route className="h-4 w-4" aria-hidden />
            </span>
            <h2
              id="formation-heading"
              className="m-0 text-lg font-semibold tracking-normal text-slate-950"
            >
              隊列予想
            </h2>
          </div>
          <p className="m-0 mt-2 text-sm text-slate-500">スタート後の想定ポジション</p>
        </div>
        <span className="rounded-md border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700">
          枠順確定後
        </span>
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="grid md:grid-cols-4">
          {formation.groups.map((group, groupIndex) => (
            <div
              key={group.key}
              className="min-w-0 border-b border-slate-200 p-4 last:border-b-0 md:border-b-0 md:border-r md:last:border-r-0"
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
                          className={`flex h-8 w-8 shrink-0 items-center justify-center rounded border text-xs font-bold ${FRAME_CLASS[horse.frame_no] ?? FRAME_CLASS[1]}`}
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
