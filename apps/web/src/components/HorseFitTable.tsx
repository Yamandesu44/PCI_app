import { ReasonList } from "@/components/ReasonList";
import { fitTone, paiBarWidth, sortByPai } from "@/lib/pace";
import type { HorseFit } from "@pci/api-client";

/** 各馬の展開適性（PAI）を、合致度の高い順にバーで可視化する。 */
export function HorseFitTable({ horses }: { horses: HorseFit[] }) {
  const sorted = sortByPai(horses);

  return (
    <ul className="horse-list">
      {sorted.map((h) => {
        const tone = fitTone(h.fit_label);
        return (
          <li key={h.horse_no} className={`horse fit-${tone}`}>
            <div className="horse-head">
              <span className="horse-no">{h.horse_no}</span>
              <span className="horse-style">{h.running_style}</span>
              <span className={`fit-badge fit-${tone}`}>{h.fit_label}</span>
              <span className="pai-value">PAI {h.pai.toFixed(0)}</span>
            </div>
            <div className="pai-bar">
              <span className={`pai-fill fit-${tone}`} style={{ width: `${paiBarWidth(h.pai)}%` }} />
            </div>
            <ReasonList reasons={h.reasons ?? []} />
          </li>
        );
      })}
    </ul>
  );
}
