import { forecastAccuracyMeta } from "@/lib/pace";
import type { ForecastAccuracy } from "@pci/api-client";

/**
 * 出走前の想定と実績の答え合わせバッジ（予測フィードバックループ）。
 *
 * 想定RPCI が保存されているレースでのみ表示する（未保存なら親側で null を渡し非表示）。
 * 実数値（RPCI・誤差）は表示しない。的中/外れを言葉と色で伝える。
 */
export function ForecastAccuracyBadge({ accuracy }: { accuracy: ForecastAccuracy }) {
  const meta = forecastAccuracyMeta(accuracy);

  return (
    <div className={`forecast-accuracy-badge forecast-accuracy-badge--${meta.tone}`}>
      <span className="forecast-accuracy-badge__label" style={{ color: meta.color }}>
        {meta.label}
      </span>
      <p className="forecast-accuracy-badge__summary">{meta.summary}</p>
    </div>
  );
}
