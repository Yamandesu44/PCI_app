import { ReasonList } from "@/components/ReasonList";
import {
  fitLabelDisplay,
  frameColorClass,
  horseNumberLabel,
  paiBarWidth,
  sortByPaceBenefit,
} from "@/lib/pace";
import type { HorseFit, StyleAdvantage } from "@pci/api-client";

/**
 * 各馬の展開適性（PAI）を、今回の流れの恩恵を受ける順にバーで可視化する。
 *
 * PAI 単独で並べない。PAI は脚質内の相対量で、脚質をまたいだ大小は
 * 「展開が向く順」を意味しないため（docs/DECISIONS.md ADR-2026-08-04）。
 */
export function HorseFitTable({
  horses,
  styleAdvantage,
}: {
  horses: HorseFit[];
  styleAdvantage?: StyleAdvantage | null;
}) {
  const sorted = sortByPaceBenefit(horses, styleAdvantage);

  return (
    <ul className="horse-list">
      {sorted.map((h) => {
        // ラベルだけでは「展開の判定」と「判断材料が足りない」を区別できない。
        // 中立の多くは後者なので、必ず併記する（docs/DECISIONS.md ADR-2026-08-04）。
        const fit = fitLabelDisplay(h);
        const tone = fit.tone;
        return (
          <li key={h.horse_no} className={`horse fit-${tone}`}>
            <div className="horse-head">
              <span
                className={`inline-flex h-7 min-w-7 shrink-0 items-center justify-center rounded border px-1 text-xs font-bold ${frameColorClass(h.frame_no)}`}
                aria-label={h.frame_no > 0 ? `${h.frame_no}枠` : "枠順未確定"}
              >
                {h.frame_no > 0 ? h.horse_no : "登録"}
              </span>
              <span className="horse-style">
                {h.horse_name ?? horseNumberLabel(h)}
              </span>
              <span className="horse-style">
                {h.frame_no > 0
                  ? h.running_style
                  : `${horseNumberLabel(h)} ・ ${h.running_style}`}
              </span>
              <span className={`fit-badge fit-${tone}`}>{h.fit_label}</span>
              {fit.lowEvidence && (
                <span
                  className="rounded border border-dashed border-current px-1 text-[10px] opacity-70"
                  title={fit.note ?? undefined}
                >
                  材料薄
                </span>
              )}
              <span className="pai-value">PAI {h.pai.toFixed(0)}</span>
            </div>
            {fit.note && <p className="text-xs opacity-70">{fit.note}</p>}
            <div className="pai-bar">
              <span
                className={`pai-fill fit-${tone}`}
                style={{ width: `${paiBarWidth(h.pai)}%` }}
              />
            </div>
            <ReasonList reasons={h.reasons ?? []} />
          </li>
        );
      })}
    </ul>
  );
}
