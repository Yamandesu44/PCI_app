import { CheckCircle2, ChevronDown, TriangleAlert, XCircle } from "lucide-react";
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
  const hasDetails =
    meta.failures.length > 0 ||
    meta.incompleteRaces.length > 0 ||
    meta.missingTrackConditionRaces.length > 0 ||
    meta.duplicateRaceGroups.length > 0 ||
    meta.recoveryCommand !== null ||
    meta.metadataRecoveryCommand !== null;
  const mobileSignals = [
    status.last_attempt_failed ? "直近失敗" : null,
    status.has_incomplete_races ? `成績未取込 ${status.incomplete_race_count}件` : null,
    status.has_missing_track_conditions
      ? `馬場情報 ${status.missing_track_condition_count}件`
      : null,
    status.has_duplicate_races ? `重複 ${status.duplicate_race_group_count}組` : null,
  ].filter((signal): signal is string => signal !== null);

  return (
    <div
      data-mobile-ingest-summary
      className={`mb-6 rounded-lg border ${tone.border} ${tone.bg} p-3 md:p-4`}
    >
      {/* モバイル(768px未満)専用の要約: 見出しと短い状態チップを表示し、
          detail文を省いて初期表示の高さを抑える。PC(md:)側は非表示。
          優先度・件数は既存の ingestStatusMeta() の判定結果をそのまま使い、
          複数異常時の選定順を独自に決めない。 */}
      <div className="flex items-center gap-2 md:hidden">
        <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-md ${tone.icon}`}>
          <Icon className="h-3.5 w-3.5" aria-hidden />
        </span>
        <p
          className="m-0 min-w-0 flex-1 truncate text-sm font-semibold"
          style={{ color: meta.color }}
        >
          {meta.headline}
        </p>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px] md:hidden">
        <span className="rounded border border-current/20 bg-white/70 px-2 py-0.5 font-semibold">
          {meta.tone === "ok" ? "正常" : "要対応"}
        </span>
        {mobileSignals.map((signal) => (
          <span key={signal} className="rounded bg-white/70 px-2 py-0.5 text-slate-700">
            {signal}
          </span>
        ))}
        {hasDetails ? <span className="font-semibold text-slate-600">詳細を確認</span> : null}
      </div>

      <div className="hidden items-start gap-3 md:flex">
        <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md ${tone.icon}`}>
          <Icon className="h-4 w-4" aria-hidden />
        </span>
        <div className="min-w-0 flex-1 max-md:hidden">
          <p className="m-0 text-sm font-semibold" style={{ color: meta.color }}>
            {meta.headline}
          </p>
          <p className="m-0 mt-1 text-sm leading-6 text-slate-700">{meta.detail}</p>
        </div>
      </div>

      <div className="mt-2 md:ml-11 md:mt-0">
        <div className="min-w-0 flex-1">
          {hasDetails ? (
            <details className="group mt-3">
              <summary className="flex min-h-11 w-fit cursor-pointer list-none items-center gap-1.5 rounded px-2 py-1 text-xs font-semibold text-slate-700 hover:bg-white/70 hover:text-slate-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 md:min-h-0">
                詳細と復旧手順
                <ChevronDown
                  className="h-3.5 w-3.5 transition-transform group-open:rotate-180"
                  aria-hidden
                />
              </summary>
              <div className="mt-3 space-y-4 border-t border-slate-200/80 pt-3">
                {meta.failures.length > 0 ? (
                  <section aria-labelledby="ingest-failures-heading">
                    <p
                      id="ingest-failures-heading"
                      className="m-0 text-xs font-semibold text-slate-800"
                    >
                      失敗の詳細（{meta.failures.length}件）
                    </p>
                    <ul className="m-0 mt-2 list-none space-y-1.5 p-0">
                      {meta.failures.map((failure, i) => (
                        <li key={i} className="rounded border border-slate-200 bg-white p-2 text-xs">
                          <span className="font-semibold text-slate-800">{failure.label}</span>
                          <span className="ml-2 text-slate-500">{failure.timestamp}</span>
                          <p className="m-0 mt-1 break-words font-mono text-[11px] text-slate-500">
                            {failure.detail}
                          </p>
                        </li>
                      ))}
                    </ul>
                  </section>
                ) : null}

                {meta.incompleteRaces.length > 0 ? (
                  <section aria-labelledby="incomplete-races-heading">
                    <p
                      id="incomplete-races-heading"
                      className="m-0 text-xs font-semibold text-slate-800"
                    >
                      成績未取込の対象（{meta.incompleteRaces.length}件）
                    </p>
                    <ul className="m-0 mt-2 grid list-none gap-1.5 p-0 sm:grid-cols-2">
                      {meta.incompleteRaces.map((race) => (
                        <li key={race.raceKey}>
                          <Link
                            href={race.href}
                            className="flex min-h-11 items-center justify-between rounded border border-amber-200 bg-white px-3 py-2 text-xs text-slate-700 hover:border-amber-300 hover:text-slate-950"
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
                  </section>
                ) : null}

                {meta.missingTrackConditionRaces.length > 0 ? (
                  <section aria-labelledby="missing-track-condition-heading">
                    <p
                      id="missing-track-condition-heading"
                      className="m-0 text-xs font-semibold text-slate-800"
                    >
                      馬場情報未反映の対象（{meta.missingTrackConditionRaces.length}件）
                    </p>
                    <ul className="m-0 mt-2 grid list-none gap-1.5 p-0 sm:grid-cols-2">
                      {meta.missingTrackConditionRaces.map((race) => (
                        <li key={race.raceKey}>
                          <Link
                            href={race.href}
                            className="flex min-h-11 items-center justify-between rounded border border-amber-200 bg-white px-3 py-2 text-xs text-slate-700 hover:border-amber-300 hover:text-slate-950"
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
                  </section>
                ) : null}

                {meta.duplicateRaceGroups.length > 0 ? (
                  <section aria-labelledby="duplicate-races-heading">
                    <p
                      id="duplicate-races-heading"
                      className="m-0 text-xs font-semibold text-slate-800"
                    >
                      重複レース（{meta.duplicateRaceGroups.length}組）
                    </p>
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
                  </section>
                ) : null}

                {meta.recoveryCommand ? (
                  <section aria-labelledby="resync-command-heading">
                    <p
                      id="resync-command-heading"
                      className="m-0 text-xs font-semibold text-slate-800"
                    >
                      再同期コマンド
                    </p>
                    <p className="m-0 mt-1 text-xs text-slate-500">リポジトリ直下で実行</p>
                    <IngestRecoveryCommand command={meta.recoveryCommand} />
                  </section>
                ) : null}

                {meta.metadataRecoveryCommand ? (
                  <section aria-labelledby="metadata-command-heading">
                    <p
                      id="metadata-command-heading"
                      className="m-0 text-xs font-semibold text-slate-800"
                    >
                      馬場情報の補完コマンド
                    </p>
                    <p className="m-0 mt-1 text-xs text-slate-500">リポジトリ直下で実行</p>
                    <IngestRecoveryCommand command={meta.metadataRecoveryCommand} />
                  </section>
                ) : null}
              </div>
            </details>
          ) : null}
        </div>
      </div>
    </div>
  );
}
