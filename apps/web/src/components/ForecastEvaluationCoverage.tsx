function clampPercent(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value * 100)));
}

export function ForecastEvaluationCoverage({
  eligibleRaceCount,
  sampleSize,
  coverageRate,
}: {
  eligibleRaceCount: number;
  sampleSize: number;
  coverageRate: number | null | undefined;
}) {
  if (eligibleRaceCount === 0) return null;

  const percentage = clampPercent(coverageRate ?? 0);
  const complete = sampleSize >= eligibleRaceCount;
  const barColor = complete ? "bg-emerald-600" : "bg-amber-500";

  return (
    <div className="mt-4 border-t border-slate-100 pt-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-xs font-semibold text-slate-700">
          事前予想の検証カバー率
        </p>
        <p className="text-xs text-slate-500">
          <span className="font-bold tabular-nums text-slate-950">
            {percentage}%
          </span>
          <span className="ml-2">
            {sampleSize} / {eligibleRaceCount}レース
          </span>
        </p>
      </div>
      <div
        className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100"
        role="progressbar"
        aria-label="事前予想の検証カバー率"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percentage}
      >
        <div
          className={`h-full rounded-full ${barColor}`}
          style={{ width: `${percentage}%` }}
        />
      </div>
      <p className="mt-1.5 text-xs text-slate-500">
        確定レースのうち、保存済みの事前予想を結果と照合できた割合
      </p>
    </div>
  );
}
