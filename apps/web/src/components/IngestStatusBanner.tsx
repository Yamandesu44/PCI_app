import { CheckCircle2, TriangleAlert, XCircle } from "lucide-react";
import Link from "next/link";

import { IngestRecoveryCommand } from "@/components/IngestRecoveryCommand";
import { ingestStatusMeta } from "@/lib/ingestStatus";
import type { IngestStatus } from "@pci/api-client";

const TONE_CLASS: Record<string, { border: string; bg: string; icon: string }> = {
  ok: { border: "border-emerald-200", bg: "bg-emerald-50", icon: "bg-emerald-100 text-emerald-700" },
  warning: { border: "border-amber-200", bg: "bg-amber-50", icon: "bg-amber-100 text-amber-700" },
  error: { border: "border-rose-200", bg: "bg-rose-50", icon: "bg-rose-100 text-rose-700" },
};

const TONE_ICON = {
  ok: CheckCircle2,
  warning: TriangleAlert,
  error: XCircle,
} as const;

/**
 * データ取り込みの鮮度・失敗状況をトップ画面上部に表示するバナー。
 *
 * `has_history=false`（開発/fixture環境等でログが無い）では何も描画しない。
 * 正常時は落ち着いた表示、鮮度低下・失敗時は目立つ表示にする。
 */
export function IngestStatusBanner({ status }: { status: IngestStatus }) {
  const meta = ingestStatusMeta(status);
  if (!meta.visible) return null;

  const tone = TONE_CLASS[meta.tone];
  const Icon = TONE_ICON[meta.tone];

  return (
    <div className={`mb-6 rounded-lg border ${tone.border} ${tone.bg} p-4`}>
      <div className="flex items-start gap-3">
        <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md ${tone.icon}`}>
          <Icon className="h-4 w-4" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <p className="m-0 text-sm font-semibold" style={{ color: meta.color }}>
            {meta.headline}
          </p>
          <p className="m-0 mt-1 text-sm leading-6 text-slate-700">{meta.detail}</p>

          {meta.failures.length > 0 ? (
            <details className="mt-2">
              <summary className="cursor-pointer text-xs font-medium text-slate-600 hover:text-slate-900">
                失敗の詳細（{meta.failures.length}件）
              </summary>
              <ul className="m-0 mt-2 list-none space-y-1.5 p-0">
                {meta.failures.map((failure, i) => (
                  <li key={i} className="rounded border border-slate-200 bg-white p-2 text-xs">
                    <span className="font-semibold text-slate-800">{failure.label}</span>
                    <span className="ml-2 text-slate-500">{failure.timestamp}</span>
                    <p className="m-0 mt-1 break-all font-mono text-[11px] text-slate-500">
                      {failure.detail}
                    </p>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}

          {meta.incompleteRaces.length > 0 ? (
            <details className="mt-2">
              <summary className="cursor-pointer text-xs font-medium text-slate-600 hover:text-slate-900">
                対象レース（{meta.incompleteRaces.length}件）
              </summary>
              <ul className="m-0 mt-2 grid list-none gap-1.5 p-0 sm:grid-cols-2">
                {meta.incompleteRaces.map((race) => (
                  <li key={race.raceKey}>
                    <Link
                      href={race.href}
                      className="flex items-center justify-between rounded border border-amber-200 bg-white px-3 py-2 text-xs text-slate-700 hover:border-amber-300 hover:text-slate-950"
                    >
                      <span className="font-semibold">{race.label}</span>
                      <span className="ml-3 text-slate-500">{race.condition}</span>
                    </Link>
                  </li>
                ))}
              </ul>
              {status.incomplete_race_count > meta.incompleteRaces.length ? (
                <p className="m-0 mt-2 text-xs text-slate-500">
                  ほか{status.incomplete_race_count - meta.incompleteRaces.length}件
                </p>
              ) : null}
            </details>
          ) : null}

          {meta.missingTrackConditionRaces.length > 0 ? (
            <details className="mt-2">
              <summary className="cursor-pointer text-xs font-medium text-slate-600 hover:text-slate-900">
                馬場情報未反映の対象（{meta.missingTrackConditionRaces.length}件）
              </summary>
              <ul className="m-0 mt-2 grid list-none gap-1.5 p-0 sm:grid-cols-2">
                {meta.missingTrackConditionRaces.map((race) => (
                  <li key={race.raceKey}>
                    <Link
                      href={race.href}
                      className="flex items-center justify-between rounded border border-amber-200 bg-white px-3 py-2 text-xs text-slate-700 hover:border-amber-300 hover:text-slate-950"
                    >
                      <span className="font-semibold">{race.label}</span>
                      <span className="ml-3 text-slate-500">{race.condition}</span>
                    </Link>
                  </li>
                ))}
              </ul>
              {status.missing_track_condition_count >
              meta.missingTrackConditionRaces.length ? (
                <p className="m-0 mt-2 text-xs text-slate-500">
                  ほか
                  {status.missing_track_condition_count -
                    meta.missingTrackConditionRaces.length}
                  件
                </p>
              ) : null}
            </details>
          ) : null}

          {meta.duplicateRaceGroups.length > 0 ? (
            <details className="mt-2">
              <summary className="cursor-pointer text-xs font-medium text-slate-600 hover:text-slate-900">
                重複レース（{meta.duplicateRaceGroups.length}組）
              </summary>
              <ul className="m-0 mt-2 grid list-none gap-1.5 p-0 sm:grid-cols-2">
                {meta.duplicateRaceGroups.map((group) => (
                  <li
                    key={`${group.label}-${group.raceKeys.join("-")}`}
                    className="rounded border border-amber-200 bg-white px-3 py-2 text-xs text-slate-700"
                  >
                    <p className="m-0 font-semibold text-slate-900">{group.label}</p>
                    <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
                      {group.raceKeys.map((raceKey) => (
                        <Link
                          key={raceKey}
                          href={`/races/${raceKey}/forecast`}
                          className="font-mono text-[11px] text-slate-600 underline decoration-slate-300 underline-offset-2 hover:text-slate-950"
                        >
                          {raceKey}
                        </Link>
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
              {status.duplicate_race_group_count > meta.duplicateRaceGroups.length ? (
                <p className="m-0 mt-2 text-xs text-slate-500">
                  ほか
                  {status.duplicate_race_group_count - meta.duplicateRaceGroups.length}組
                </p>
              ) : null}
            </details>
          ) : null}

          {meta.recoveryCommand ? (
            <details className="mt-2">
              <summary className="cursor-pointer text-xs font-medium text-slate-600 hover:text-slate-900">
                再同期コマンド
              </summary>
              <p className="m-0 mt-2 text-xs text-slate-500">リポジトリ直下で実行</p>
              <IngestRecoveryCommand command={meta.recoveryCommand} />
            </details>
          ) : null}

          {meta.metadataRecoveryCommand ? (
            <details className="mt-2">
              <summary className="cursor-pointer text-xs font-medium text-slate-600 hover:text-slate-900">
                馬場情報の補完コマンド
              </summary>
              <p className="m-0 mt-2 text-xs text-slate-500">リポジトリ直下で実行</p>
              <IngestRecoveryCommand command={meta.metadataRecoveryCommand} />
            </details>
          ) : null}
        </div>
      </div>
    </div>
  );
}
