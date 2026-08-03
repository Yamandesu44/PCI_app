import type { ForecastPerformanceGroup } from "@pci/api-client";

const BAR_COLORS: Record<string, string> = {
  strong: "bg-emerald-600",
  normal: "bg-sky-600",
  caution: "bg-amber-500",
};

const DEFAULT_CONFIDENCE_REVIEW_TARGET = 100;

function percentLabel(value: number | null | undefined): string {
  return value == null ? "集計なし" : `${Math.round(value * 100)}%`;
}

export function ForecastConfidenceCalibration({
  groups,
  cohortGroups = [],
  reviewTarget = DEFAULT_CONFIDENCE_REVIEW_TARGET,
  reviewReady,
}: {
  groups: ForecastPerformanceGroup[];
  cohortGroups?: ForecastPerformanceGroup[];
  reviewTarget?: number;
  reviewReady?: boolean;
}) {
  const turfCount = cohortGroups.find((group) => group.key === "turf")?.sample_size ?? 0;
  const dirtCount = cohortGroups.find((group) => group.key === "dirt")?.sample_size ?? 0;
  const isReviewReady = reviewReady ?? (
    turfCount >= reviewTarget && dirtCount >= reviewTarget
  );
  const turfRemaining = Math.max(reviewTarget - turfCount, 0);
  const dirtRemaining = Math.max(reviewTarget - dirtCount, 0);

  return (
    <div className="mt-5 border-t border-slate-100 pt-5">
      <h3 className="text-sm font-bold text-slate-900">信頼度別の一致率</h3>
      <p className="mt-1 text-xs text-slate-500">
        新しい読みやすさ指標で保存された予想のみを集計
      </p>
      <p
        className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs font-semibold tabular-nums text-slate-700"
        aria-label={`新指標の蓄積状況 芝${turfCount}件、ダート${dirtCount}件、各${reviewTarget}件で再評価`}
      >
        <span>芝 {turfCount}/{reviewTarget}</span>
        <span>ダート {dirtCount}/{reviewTarget}</span>
        {isReviewReady ? (
          <span className="text-emerald-700">再評価可能</span>
        ) : (
          <span className="font-normal text-slate-500">
            残り 芝{turfRemaining}件・ダート{dirtRemaining}件
          </span>
        )}
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
