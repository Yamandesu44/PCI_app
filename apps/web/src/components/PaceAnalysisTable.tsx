import { pciTone, pciToneColor, pciToneLabel } from "@/lib/pace";
import type { HorsePaceAnalysis } from "@pci/api-client";

/** 確定後の各馬 PCI を着順で並べて表示。PCI3 寄与馬（上位3着）を強調する。 */
export function PaceAnalysisTable({ horses }: { horses: HorsePaceAnalysis[] }) {
  return (
    <table className="pci-table">
      <thead>
        <tr>
          <th>着</th>
          <th>馬番</th>
          <th>馬名</th>
          <th>脚質</th>
          <th>PCI</th>
          <th>傾向</th>
          <th>上がり3F</th>
        </tr>
      </thead>
      <tbody>
        {horses.map((h) => {
          const tone = pciTone(h.pci);
          return (
            <tr key={h.horse_no} className={h.is_pci3_contributor ? "pci3" : undefined}>
              <td>{h.finish_pos ?? "—"}</td>
              <td>
                <span className="horse-no sm">{h.horse_no}</span>
                {h.is_pci3_contributor ? <span className="pci3-mark">★</span> : null}
              </td>
              <td>{h.horse_name ?? "—"}</td>
              <td>{h.running_style ?? "—"}</td>
              <td className="num">{h.pci !== null && h.pci !== undefined ? h.pci.toFixed(1) : "—"}</td>
              <td>
                <span className="tone-tag" style={{ color: pciToneColor(tone) }}>
                  {pciToneLabel(tone)}
                </span>
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
