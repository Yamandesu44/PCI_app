import { Wind } from "lucide-react";

import { frameColorClass, horseNumberLabel } from "@/lib/pace";
import type { IntegratedEntry, IntegratedRanking } from "@pci/api-client";

function abilityTag(tier: string): { label: string; chip: string } {
  if (tier === "上位")
    return { label: "能力上位", chip: "bg-slate-900 text-white" };
  if (tier === "中位")
    return { label: "能力中位", chip: "bg-slate-100 text-slate-700" };
  if (tier === "下位")
    return { label: "能力下位", chip: "bg-slate-50 text-slate-500" };
  return { label: "能力評価難", chip: "bg-slate-50 text-slate-400" };
}

function fitTag(fitLabel: string): { label: string; chip: string } | null {
  if (fitLabel === "合致")
    return { label: "展開が向く", chip: "bg-emerald-100 text-emerald-800" };
  if (fitLabel === "不利")
    return { label: "展開が向きにくい", chip: "bg-rose-100 text-rose-700" };
  return null; // 中立はタグを付けず情報量を絞る
}

function entryName(entry: IntegratedEntry): string {
  return entry.horse_name ?? horseNumberLabel(entry);
}

function Tag({ label, chip }: { label: string; chip: string }) {
  return (
    <span
      className={`shrink-0 rounded px-1.5 py-0.5 text-[11px] font-semibold ${chip}`}
    >
      {label}
    </span>
  );
}

function HorseRows({
  entries,
  showRank,
  highlight = false,
}: {
  entries: IntegratedEntry[];
  showRank: boolean;
  highlight?: boolean;
}) {
  return (
    <ol className="m-0 grid list-none gap-2 p-0">
      {entries.map((entry) => {
        const ability = abilityTag(entry.ability_tier);
        const fit = fitTag(entry.fit_label);
        return (
          <li
            key={entry.horse_no}
            className={`flex items-start gap-3 rounded-lg border p-3 shadow-sm ${
              highlight
                ? "border-emerald-200 bg-emerald-50/50"
                : "border-slate-200 bg-white"
            }`}
          >
            {showRank ? (
              <span className="flex shrink-0 flex-col items-center justify-center">
                <span className="text-base font-semibold leading-none text-slate-500">
                  {entry.rank}
                </span>
                <span className="mt-0.5 text-[10px] font-medium text-slate-400">
                  番目
                </span>
              </span>
            ) : null}
            <span
              className={`flex h-9 w-9 shrink-0 items-center justify-center rounded border text-xs font-bold ${frameColorClass(entry.frame_no)}`}
              aria-label={
                entry.frame_no > 0 ? `${entry.frame_no}枠` : "枠順未確定"
              }
            >
              {entry.frame_no > 0 ? entry.horse_no : "登録"}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <p className="m-0 truncate text-sm font-semibold text-slate-950">
                  {entryName(entry)}
                </p>
                {fit ? <Tag label={fit.label} chip={fit.chip} /> : null}
                <Tag label={ability.label} chip={ability.chip} />
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
 * 想定される流れが向く馬を主役に置き、能力の並びは補助として畳む。
 *
 * 以前は「近走内容による能力の並び」を見出しにし、前置きで
 * 「この並びは単勝人気の順より当たりません」と断っていた。実測（1位馬の勝率
 * 20.2% 対 単勝人気1位 36.9%・ADR-2026-08-04）に忠実ではあったが、
 * **自分の看板を自分で否定する構成**で、最初に目に入る情報がそれになっていた。
 *
 * 製品の価値は展開の読みと、それが向く馬を挙げられること。そちらを前に出し、
 * 能力の並びは「補足の材料」という位置づけに戻す。順位が当たらないという事実は
 * 消さず、能力の並びを開いたところに範囲を限って残す（予想検証ページにも実測がある）。
 *
 * **向く馬は馬番順に並べる。** 能力順にすると先頭が推奨に見えるが、それは実測で
 * 否定された使い方そのもの。PAI で馬をまたいで順位を付けないという方針とも揃える
 * （ADR-2026-08-04）。
 */
export function IntegratedRankingView({
  ranking,
}: {
  ranking: IntegratedRanking;
}) {
  const entries = [...(ranking.entries ?? [])].sort((a, b) => a.rank - b.rank);
  if (entries.length === 0) return null;

  const suited = entries
    .filter((e) => e.fit_label === "合致")
    .sort((a, b) => a.horse_no - b.horse_no);
  const others = entries.filter((e) => e.fit_label !== "合致");

  return (
    <section aria-labelledby="integrated-heading">
      <div className="mb-4">
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-md bg-emerald-50 text-emerald-700">
            <Wind className="h-4 w-4" aria-hidden />
          </span>
          <h2
            id="integrated-heading"
            className="m-0 text-base font-semibold tracking-normal text-slate-800"
          >
            この展開が向きそうな馬
          </h2>
        </div>
        <p className="m-0 mt-2 text-sm text-slate-500">
          {suited.length > 0
            ? "想定される流れで持ち味を出しやすい馬です（馬番順）。"
            : "今回は、想定される流れが特に向くと言える馬がいません。"}
          <strong className="font-semibold text-slate-700">
            買うべき馬の推奨ではありません。
          </strong>
        </p>
      </div>

      {suited.length > 0 ? (
        <HorseRows entries={suited} showRank={false} highlight />
      ) : null}

      {others.length > 0 ? (
        <details
          className="mt-3 rounded-lg border border-slate-200 bg-white px-3 py-2"
          open={suited.length === 0}
        >
          <summary className="cursor-pointer text-sm font-semibold text-slate-700">
            近走内容による能力の並びを見る（{others.length}頭）
          </summary>
          <p className="m-0 mt-2 text-xs leading-5 text-slate-500">
            近走の着順内容から推定した相対評価です。
            <strong className="font-semibold text-slate-600">
              勝ち馬を当てるための順位ではありません。
            </strong>
            展開が向くかどうかを確かめる材料としてお使いください。
          </p>
          <div className="mt-3">
            <HorseRows entries={others} showRank />
          </div>
        </details>
      ) : null}

      <p className="m-0 mt-3 text-xs leading-5 text-slate-400">
        ※ 展開の向き不向きは、各馬の脚質と想定されるペースから算出しています。
        馬の力そのものの評価ではありません。
      </p>
    </section>
  );
}
