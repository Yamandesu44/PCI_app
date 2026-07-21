import { Trophy } from "lucide-react";

import { horseNumberLabel } from "@/lib/pace";
import type { IntegratedEntry, IntegratedRanking } from "@pci/api-client";

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

// 分類タグ（記号ではなく言葉タグで表す）。無印はタグを付けない。
const CATEGORY_TAG: Record<string, { label: string; chip: string; row: string }> = {
  本命: { label: "本命", chip: "bg-emerald-600 text-white", row: "border-emerald-300 bg-emerald-50/70" },
  対抗: { label: "対抗", chip: "bg-blue-600 text-white", row: "border-blue-200 bg-blue-50/50" },
  穴: { label: "穴（妙味）", chip: "bg-amber-500 text-white", row: "border-amber-200 bg-amber-50/50" },
  危険: { label: "人気でも注意", chip: "bg-rose-600 text-white", row: "border-rose-200 bg-rose-50/50" },
};

function abilityTag(tier: string): { label: string; chip: string } | null {
  if (tier === "上位") return { label: "能力上位", chip: "bg-slate-900 text-white" };
  if (tier === "中位") return { label: "能力中位", chip: "bg-slate-100 text-slate-700" };
  if (tier === "下位") return { label: "能力下位", chip: "bg-slate-50 text-slate-500" };
  return { label: "能力評価難", chip: "bg-slate-50 text-slate-400" };
}

function fitTag(fitLabel: string): { label: string; chip: string } | null {
  if (fitLabel === "合致") return { label: "展開が向く", chip: "bg-emerald-100 text-emerald-800" };
  if (fitLabel === "不利") return { label: "展開が向きにくい", chip: "bg-rose-100 text-rose-700" };
  return null; // 中立はタグを付けず情報量を絞る
}

function entryName(entry: IntegratedEntry): string {
  return entry.horse_name ?? horseNumberLabel(entry);
}

function Tag({ label, chip }: { label: string; chip: string }) {
  return (
    <span className={`shrink-0 rounded px-1.5 py-0.5 text-[11px] font-semibold ${chip}`}>{label}</span>
  );
}

/**
 * 統合順位予想（展開×能力）。総合順位を主役に、分類は◎○▲△の印ではなく言葉タグで表す。
 */
export function IntegratedRankingView({ ranking }: { ranking: IntegratedRanking }) {
  const entries = ranking.entries ?? [];
  if (entries.length === 0) return null;

  return (
    <section aria-labelledby="integrated-heading">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-md bg-amber-50 text-amber-700">
              <Trophy className="h-4 w-4" aria-hidden />
            </span>
            <h2
              id="integrated-heading"
              className="m-0 text-lg font-semibold tracking-normal text-slate-950"
            >
              統合順位予想
            </h2>
          </div>
          <p className="m-0 mt-2 text-sm text-slate-500">
            地力（近走内容）と想定される流れへの適性を合わせた総合順位。分類はタグで表示します。
          </p>
        </div>
      </div>

      <ol className="m-0 grid list-none gap-2 p-0">
        {entries.map((entry) => {
          const category = CATEGORY_TAG[entry.mark] ?? null;
          const ability = abilityTag(entry.ability_tier);
          const fit = fitTag(entry.fit_label);
          const rowClass = category?.row ?? "border-slate-200 bg-white";
          return (
            <li
              key={entry.horse_no}
              className={`flex items-start gap-3 rounded-lg border p-3 shadow-sm ${rowClass}`}
            >
              <span className="flex shrink-0 flex-col items-center justify-center">
                <span className="text-xl font-bold leading-none text-slate-900">{entry.rank}</span>
                <span className="mt-0.5 text-[10px] font-medium text-slate-400">位</span>
              </span>
              <span
                className={`flex h-9 w-9 shrink-0 items-center justify-center rounded border text-xs font-bold ${FRAME_CLASS[entry.frame_no] ?? FRAME_CLASS[1]}`}
                aria-label={entry.frame_no > 0 ? `${entry.frame_no}枠` : "枠順未確定"}
              >
                {entry.horse_no}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="m-0 truncate text-sm font-semibold text-slate-950">
                    {entryName(entry)}
                  </p>
                  {category ? <Tag label={category.label} chip={category.chip} /> : null}
                  {ability ? <Tag label={ability.label} chip={ability.chip} /> : null}
                  {fit ? <Tag label={fit.label} chip={fit.chip} /> : null}
                </div>
                {entry.reasons[0] ? (
                  <p className="m-0 mt-1 text-xs leading-5 text-slate-600">
                    {entry.reasons[0].description}
                  </p>
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>
      <p className="m-0 mt-3 text-xs leading-5 text-slate-400">
        ※ 地力は近走の着順内容から推定した相対評価です。「穴（妙味）」は地力中位でも展開が向けば上位進出の
        余地がある馬、「人気でも注意」は地力上位でも今回の流れが向きにくい馬です。
      </p>
    </section>
  );
}
