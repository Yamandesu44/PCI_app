import type { ForecastPerformanceGroup } from "@pci/api-client";

const BAR_COLORS: Record<string, string> = {
  strong: "bg-emerald-600",
  normal: "bg-sky-600",
  caution: "bg-amber-500",
};

function percentLabel(value: number | null | undefined): string {
  return value == null ? "集計なし" : `${Math.round(value * 100)}%`;
}

export function ForecastConfidenceCalibration({
  groups,
}: {
  groups: ForecastPerformanceGroup[];
}) {
  return (
    <div className="mt-5 border-t border-slate-100 pt-5">
      <h3 className="text-sm font-bold text-slate-900">信頼度別の一致率</h3>
      <p className="mt-1 text-xs text-slate-500">
        画面に表示する信頼度区分ごとの検証結果
      </p>

      <dl className="mt-4 grid gap-4">
        {groups.map((group) => {
          const percentage =
            group.hit_rate == null ? 0 : Math.round(group.hit_rate * 100);
          return (
            <div key={group.key}>
              <div className="flex items-baseline justify-between gap-3">
                <dt className="text-xs font-semibold text-slate-700">
                  {group.label}
                </dt>
                <dd className="text-xs text-slate-500">
                  <span className="font-bold tabular-nums text-slate-950">
                    {percentLabel(group.hit_rate)}
                  </span>
                  <span className="ml-2">{group.sample_size}レース</span>
                </dd>
              </div>
              <div
                className="mt-1.5 h-2 overflow-hidden rounded-full bg-slate-100"
                role="progressbar"
                aria-label={`${group.label}の一致率`}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={group.hit_rate == null ? undefined : percentage}
              >
                <div
                  className={[
                    "h-full rounded-full",
                    BAR_COLORS[group.key] ?? "bg-slate-500",
                  ].join(" ")}
                  style={{ width: `${percentage}%` }}
                />
              </div>
            </div>
          );
        })}
      </dl>
    </div>
  );
}
