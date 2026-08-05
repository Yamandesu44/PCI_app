import { ListOrdered } from "lucide-react";

import { frameColorClass, horseNumberLabel } from "@/lib/pace";
import type { IntegratedEntry, IntegratedRanking } from "@pci/api-client";

// 2026-08-04: 「本命/対抗/穴/危険」という買い目の印は表示しない。
// 期間外500レースで、この順位の1位馬は勝率20.2%と単勝人気順の36.9%を大きく下回った
// （docs/DECISIONS.md ADR-2026-08-04）。当たらない印を推奨として出さない。
// 能力の段階と展開の向き不向きという「事実」だけをタグで示す。
const CATEGORY_TAG: Record<string, { label: string; chip: string; row: string }> = {};

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

function RankingRows({ entries }: { entries: IntegratedEntry[] }) {
  return (
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
              <span className="text-base font-semibold leading-none text-slate-500">{entry.rank}</span>
              <span className="mt-0.5 text-[10px] font-medium text-slate-400">番目</span>
            </span>
            <span
              className={`flex h-9 w-9 shrink-0 items-center justify-center rounded border text-xs font-bold ${frameColorClass(entry.frame_no)}`}
              aria-label={entry.frame_no > 0 ? `${entry.frame_no}枠` : "枠順未確定"}
            >
              {entry.frame_no > 0 ? entry.horse_no : "登録"}
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
  );
}

/**
 * 近走内容による能力の並び（参考）。買い目の推奨ではない。
 *
 * 2026-08-04の実測で、この順位は単勝人気順に大きく劣ることが確定した
 * （1位馬の勝率 20.2% 対 36.9%）。予想として提示すると利用者を誤らせるため、
 * 見出し・順位表記・印を落とし、展開解説の補助情報として置く。
 */
export function IntegratedRankingView({ ranking }: { ranking: IntegratedRanking }) {
  const entries = [...(ranking.entries ?? [])].sort((a, b) => a.rank - b.rank);
  if (entries.length === 0) return null;
  const primaryEntries = entries.slice(0, 5);
  const remainingEntries = entries.slice(5);

  return (
    <section aria-labelledby="integrated-heading">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-md bg-slate-100 text-slate-600">
              <ListOrdered className="h-4 w-4" aria-hidden />
            </span>
            <h2
              id="integrated-heading"
              className="m-0 text-base font-semibold tracking-normal text-slate-800"
            >
              近走内容による能力の並び（参考）
            </h2>
          </div>
          <p className="m-0 mt-2 text-sm text-slate-500">
            各馬の近走から算出した地力の順です。
            <strong className="font-semibold text-slate-700">買うべき馬の推奨ではありません。</strong>
            この並びは単勝人気の順より当たりません。展開が向くかどうかの判断材料としてお使いください。
          </p>
        </div>
      </div>

      <RankingRows entries={primaryEntries} />
      {remainingEntries.length > 0 ? (
        <details className="mt-3 rounded-lg border border-slate-200 bg-white px-3 py-2">
          <summary className="cursor-pointer text-sm font-semibold text-slate-700">
            6位以下を表示（{remainingEntries.length}頭）
          </summary>
          <div className="mt-3">
            <RankingRows entries={remainingEntries} />
          </div>
        </details>
      ) : null}
      <p className="m-0 mt-3 text-xs leading-5 text-slate-400">
        ※ 地力は近走の着順内容から推定した相対評価です。過去500レースの検証では、
        この並びの1番目の馬より、単勝人気1位の馬のほうが好走しました。
        買う馬を決める用途には向きません。「展開が向く」馬を探す手がかりとしてお使いください。
      </p>
    </section>
  );
}
