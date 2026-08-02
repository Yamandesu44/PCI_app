"use client";

interface PaceProfileChartProps {
  data: Array<{
    style: string;
    value: number;
    /** 展開から有利不利を断定できない脚質（差し・追込）。淡く描いて主張を弱める。 */
    muted?: boolean;
  }>;
}

function clampPercent(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)));
}

export function PaceProfileChart({ data }: PaceProfileChartProps) {
  return (
    <div className="grid gap-3">
      {data.map((item) => {
        const value = clampPercent(item.value);
        return (
          <div key={item.style} className="grid gap-1.5">
            <div className="flex items-center justify-between gap-3 text-sm">
              <span
                className={`font-semibold ${item.muted ? "text-slate-400" : "text-slate-800"}`}
              >
                {item.style}
                {item.muted ? <span className="ml-1.5 text-xs font-normal">（参考）</span> : null}
              </span>
              <span
                className={`font-mono text-xs font-semibold ${
                  item.muted ? "text-slate-400" : "text-slate-500"
                }`}
              >
                {value}
              </span>
            </div>
            <div className="h-3 overflow-hidden rounded-full bg-slate-100">
              <div
                className={`h-full rounded-full transition-[width] duration-300 ${
                  item.muted ? "bg-slate-300" : "bg-slate-950"
                }`}
                style={{ width: `${value}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
