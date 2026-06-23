"use client";

interface PaceProfileChartProps {
  data: Array<{
    style: string;
    value: number;
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
              <span className="font-semibold text-slate-800">{item.style}</span>
              <span className="font-mono text-xs font-semibold text-slate-500">{value}</span>
            </div>
            <div className="h-3 overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-slate-950 transition-[width] duration-300"
                style={{ width: `${value}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
