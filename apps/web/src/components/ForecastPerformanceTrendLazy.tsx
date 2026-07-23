"use client";

import dynamic from "next/dynamic";
import type { ForecastPerformanceTrendPoint } from "@pci/api-client";

const ForecastPerformanceTrend = dynamic(
  () =>
    import("@/components/ForecastPerformanceTrend").then(
      (module) => module.ForecastPerformanceTrend,
    ),
  {
    ssr: false,
    loading: () => (
      <div
        className="mt-5 h-56 animate-pulse border-t border-slate-100 bg-slate-50"
        aria-hidden
      />
    ),
  },
);

export function ForecastPerformanceTrendLazy({
  points,
}: {
  points: ForecastPerformanceTrendPoint[];
}) {
  return <ForecastPerformanceTrend points={points} />;
}
