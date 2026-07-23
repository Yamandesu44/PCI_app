"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ForecastPerformanceTrendPoint } from "@pci/api-client";

function shortDate(value: string): string {
  const month = Number(value.slice(5, 7));
  const day = Number(value.slice(8, 10));
  return `${month}/${day}`;
}

function percentLabel(value: number | null | undefined): string {
  return value == null ? "集計なし" : `${Math.round(value * 100)}%`;
}

export function ForecastPerformanceTrend({
  points,
}: {
  points: ForecastPerformanceTrendPoint[];
}) {
  const data = points.map((point) => ({
    label: shortDate(point.date_from),
    period: `${shortDate(point.date_from)} - ${shortDate(point.date_to)}`,
    rate: point.hit_rate == null ? null : Math.round(point.hit_rate * 100),
    sampleSize: point.sample_size,
  }));
  const latest = [...points].reverse().find((point) => point.sample_size > 0);

  return (
    <div className="mt-5 border-t border-slate-100 pt-5">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h3 className="text-sm font-bold text-slate-900">週別の一致率</h3>
          <p className="mt-1 text-xs text-slate-500">
            進行中の週を除いた直近8週間
          </p>
        </div>
        {latest ? (
          <p className="text-right text-xs text-slate-500">
            最新週
            <span className="ml-2 font-bold tabular-nums text-slate-900">
              {percentLabel(latest.hit_rate)}
            </span>
            <span className="ml-2">{latest.sample_size}レース</span>
          </p>
        ) : null}
      </div>

      <div
        className="mt-3 h-44 w-full"
        role="img"
        aria-label="直近8完了週の展開予想一致率"
      >
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: 4 }}>
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" vertical={false} />
            <XAxis
              axisLine={false}
              dataKey="label"
              interval="preserveStartEnd"
              tick={{ fill: "#64748b", fontSize: 10 }}
              tickLine={false}
            />
            <YAxis domain={[0, 100]} hide />
            <Tooltip
              cursor={{ fill: "#f1f5f9" }}
              formatter={(value) => [`${Number(value)}%`, "一致率"]}
              labelFormatter={(_, payload) => {
                const item = payload[0]?.payload as
                  | { period?: string; sampleSize?: number }
                  | undefined;
                return item
                  ? `${item.period} / ${item.sampleSize ?? 0}レース`
                  : "";
              }}
              contentStyle={{
                borderColor: "#cbd5e1",
                borderRadius: 6,
                boxShadow: "0 4px 12px rgb(15 23 42 / 0.08)",
                fontSize: 12,
              }}
            />
            <Bar
              dataKey="rate"
              fill="#059669"
              maxBarSize={42}
              minPointSize={2}
              radius={[3, 3, 0, 0]}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
