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

// 統合分類記号（◎○▲△）と色。危険は注意を促す配色にする。
const MARK_META: Record<string, { symbol: string; label: string; chip: string; row: string }> = {
  本命: {
    symbol: "◎",
    label: "本命",
    chip: "bg-emerald-600 text-white",
    row: "border-emerald-300 bg-emerald-50/70",
  },
  対抗: {
    symbol: "○",
    label: "対抗",
    chip: "bg-blue-600 text-white",
    row: "border-blue-200 bg-blue-50/60",
  },
  穴: {
    symbol: "▲",
    label: "穴",
    chip: "bg-amber-500 text-white",
    row: "border-amber-200 bg-amber-50/60",
  },
  危険: {
    symbol: "△",
    label: "危険",
    chip: "bg-rose-600 text-white",
    row: "border-rose-200 bg-rose-50/60",
  },
  無印: {
    symbol: "—",
    label: "無印",
    chip: "bg-slate-200 text-slate-600",
    row: "border-slate-200 bg-white",
  },
};

const FALLBACK_MARK = MARK_META["無印"];

// 展開との相性ラベル（PAI由来）を平易な言葉へ翻訳する（実数は出さない方針）。
function fitPhrase(fitLabel: string): string {
  if (fitLabel === "合致") return "展開が向く";
  if (fitLabel === "不利") return "展開が向きにくい";
  return "展開は普通";
}

function fitClass(fitLabel: string): string {
  if (fitLabel === "合致") return "bg-emerald-100 text-emerald-800";
  if (fitLabel === "不利") return "bg-rose-100 text-rose-700";
  return "bg-slate-100 text-slate-600";
}

function abilityClass(tier: string): string {
  if (tier === "上位") return "bg-slate-900 text-white";
  if (tier === "中位") return "bg-slate-100 text-slate-700";
  if (tier === "下位") return "bg-slate-50 text-slate-500";
  return "bg-slate-50 text-slate-400";
}

function entryName(entry: IntegratedEntry): string {
  return entry.horse_name ?? horseNumberLabel(entry);
}

/**
 * 統合順位予想（展開×能力の2軸分類）。
 * 地力（能力）と想定される流れへの適性を掛け合わせ、本命/対抗/穴/危険で提示する。
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
            地力（近走内容）と想定される流れへの適性の2軸で総合評価
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs font-semibold text-slate-500">
          <span>◎本命</span>
          <span>○対抗</span>
          <span>▲穴</span>
          <span className="text-rose-600">△危険</span>
        </div>
      </div>

      <ol className="m-0 grid list-none gap-2 p-0">
        {entries.map((entry) => {
          const mark = MARK_META[entry.mark] ?? FALLBACK_MARK;
          return (
            <li
              key={entry.horse_no}
              className={`flex items-start gap-3 rounded-lg border p-3 shadow-sm ${mark.row}`}
            >
              <span className="mt-0.5 w-6 shrink-0 text-center text-sm font-bold text-slate-400">
                {entry.rank}
              </span>
              <span
                className={`flex h-9 shrink-0 items-center gap-1 rounded-md px-2 text-sm font-bold ${mark.chip}`}
              >
                <span aria-hidden>{mark.symbol}</span>
                {mark.label}
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
                  <span
                    className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold ${abilityClass(entry.ability_tier)}`}
                  >
                    能力{entry.ability_tier}
                  </span>
                  <span
                    className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold ${fitClass(entry.fit_label)}`}
                  >
                    {fitPhrase(entry.fit_label)}
                  </span>
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
        ※ 地力は近走の着順内容から推定した相対評価です（人気・オッズ・賞金は未使用）。
      </p>
    </section>
  );
}
