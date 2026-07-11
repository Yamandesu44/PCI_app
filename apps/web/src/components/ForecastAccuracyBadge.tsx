import { forecastAccuracyMeta } from "@/lib/pace";
import type { ForecastAccuracy } from "@pci/api-client";
import { CheckCircle2, TriangleAlert } from "lucide-react";

/**
 * 出走前の想定と実績の答え合わせバッジ（予測フィードバックループ）。
 *
 * 想定RPCI が保存されているレースでのみ表示する（未保存なら親側で null を渡し非表示）。
 * 実数値（RPCI・誤差）は表示しない。的中/外れを言葉と色で伝える。
 */
export function ForecastAccuracyBadge({ accuracy }: { accuracy: ForecastAccuracy }) {
  const meta = forecastAccuracyMeta(accuracy);
  const isHit = meta.tone === "hit";
  const Icon = isHit ? CheckCircle2 : TriangleAlert;

  return (
    <div
      className={[
        "flex items-start gap-3 rounded-lg border p-4 shadow-sm",
        isHit ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50",
      ].join(" ")}
    >
      <span
        className={[
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-md",
          isHit ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700",
        ].join(" ")}
      >
        <Icon className="h-5 w-5" aria-hidden />
      </span>
      <div>
        <span className="block text-sm font-semibold" style={{ color: meta.color }}>
          {meta.label}
        </span>
        <p className="m-0 mt-1 text-sm leading-6 text-slate-700">{meta.summary}</p>
      </div>
    </div>
  );
}
