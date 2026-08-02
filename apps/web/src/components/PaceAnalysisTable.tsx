import { frameColorClass, paceSpeedFromIndex } from "@/lib/pace";
import type { HorsePaceAnalysis } from "@pci/api-client";

interface PaceAnalysisTableProps {
  horses: HorsePaceAnalysis[];
  trackType: string | null | undefined;
}

/** 確定後の各馬 PCI を着順で並べて表示。PCI3 寄与馬（上位3着）を強調する。 */
export function PaceAnalysisTable({ horses, trackType }: PaceAnalysisTableProps) {
  return (
    <table className="pci-table">
      <thead>
        <tr>
          <th>着</th>
          <th>馬番</th>
          <th>馬名</th>
          <th>脚質</th>
          <th>ペース傾向</th>
          <th aria-label="傾向記号">傾向</th>
          <th>上がり3F</th>
        </tr>
      </thead>
      <tbody>
        {horses.map((h) => {
          const speed = paceSpeedFromIndex(h.pci, trackType);
          return (
            <tr key={h.horse_no} className={h.is_pci3_contributor ? "pci3" : undefined}>
              <td>{h.finish_pos ?? "—"}</td>
              <td>
                <span
                  className={`inline-flex h-6 min-w-6 items-center justify-center rounded border px-1 text-xs font-bold ${frameColorClass(h.frame_no)}`}
                  aria-label={h.frame_no > 0 ? `${h.frame_no}枠` : "枠順未確定"}
                >
                  {h.frame_no > 0 ? h.horse_no : "登録"}
                </span>
                {h.is_pci3_contributor ? <span className="pci3-mark">★</span> : null}
              </td>
              <td>{h.horse_name ?? "—"}</td>
              <td>{h.running_style ?? "—"}</td>
              <td>
                <span className="tone-tag" style={{ color: speed.color }}>
                  {speed.label}
                </span>
              </td>
              <td className="num" style={{ color: speed.color }}>
                {speed.symbol}
              </td>
              <td className="num">
                {h.agari_3f_s !== null && h.agari_3f_s !== undefined
                  ? `${h.agari_3f_s.toFixed(1)}秒`
                  : "—"}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
