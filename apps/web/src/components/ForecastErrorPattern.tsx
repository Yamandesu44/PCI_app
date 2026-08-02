import { ChevronDown } from "lucide-react";
import type { ForecastPaceMatrixRow } from "@pci/api-client";

const SHORT_LABELS: Record<string, string> = {
  high: "速い",
  average: "平均",
  slow: "落ち着く",
};

function rateLabel(rate: number | null | undefined): string {
  return rate == null ? "—" : `${Math.round(rate * 100)}%`;
}

function cellTone(matched: boolean, count: number): string {
  if (count === 0) return "text-slate-400";
  return matched
    ? "bg-emerald-50 text-emerald-800"
    : "bg-amber-50 text-amber-800";
}

export function ForecastErrorPattern({
  rows,
}: {
  rows: ForecastPaceMatrixRow[];
}) {
  const total = rows.reduce((sum, row) => sum + row.sample_size, 0);
  if (total === 0) return null;

  return (
    <details className="group mt-5 border-t border-slate-100 pt-5">
      <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-4 text-left">
        <div>
          <h3 className="text-sm font-bold text-slate-900">外れ方の傾向</h3>
          <p className="mt-1 text-xs text-slate-500">
            予想した流れと、実際の流れの組み合わせ
          </p>
        </div>
        <ChevronDown
          className="h-4 w-4 shrink-0 text-slate-400 transition-transform group-open:rotate-180"
          aria-hidden
        />
      </summary>

      <div className="mt-4 overflow-x-auto">
        <div className="min-w-[430px] border border-slate-200 text-xs">
          <div className="grid grid-cols-[112px_repeat(3,minmax(88px,1fr))] border-b border-slate-200 bg-slate-50 font-semibold text-slate-600">
            <div className="px-3 py-2.5">予想 ＼ 実際</div>
            {rows[0]?.cells.map((cell) => (
              <div
                className="border-l border-slate-200 px-2 py-2.5 text-center"
                key={cell.key}
              >
                {SHORT_LABELS[cell.key] ?? cell.label}
              </div>
            ))}
          </div>

          {rows.map((row) => (
            <div
              className="grid grid-cols-[112px_repeat(3,minmax(88px,1fr))] border-b border-slate-100 last:border-b-0"
              key={row.predicted_key}
            >
              <div className="flex flex-col justify-center px-3 py-2.5">
                <span className="font-semibold text-slate-800">
                  {SHORT_LABELS[row.predicted_key] ?? row.predicted_label}
                </span>
                <span className="mt-0.5 text-[11px] text-slate-500">
                  {row.sample_size}レース
                </span>
              </div>
              {row.cells.map((cell) => {
                const matched = row.predicted_key === cell.key;
                return (
                  <div
                    className={[
                      "flex flex-col items-center justify-center border-l border-slate-100 px-2 py-2.5",
                      cellTone(matched, cell.count),
                    ].join(" ")}
                    key={cell.key}
                  >
                    <span className="font-bold tabular-nums">
                      {rateLabel(cell.rate)}
                    </span>
                    <span className="mt-0.5 text-[11px]">{cell.count}件</span>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </details>
  );
}
