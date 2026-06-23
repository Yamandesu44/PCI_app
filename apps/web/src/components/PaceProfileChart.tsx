"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface PaceProfileChartProps {
  data: Array<{
    style: string;
    value: number;
  }>;
}

export function PaceProfileChart({ data }: PaceProfileChartProps) {
  return (
    <div className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
          <CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="style" tickLine={false} axisLine={false} fontSize={12} />
          <YAxis hide domain={[0, 100]} />
          <Tooltip
            cursor={{ fill: "rgba(15, 23, 42, 0.04)" }}
            formatter={(value) => [`${Number(value).toFixed(0)}`, "有利度"]}
            labelStyle={{ color: "#0f172a", fontWeight: 700 }}
            contentStyle={{
              border: "1px solid #e5e7eb",
              borderRadius: 8,
              boxShadow: "0 12px 30px rgba(15, 23, 42, 0.08)",
            }}
          />
          <Bar dataKey="value" fill="#0f172a" radius={[6, 6, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
