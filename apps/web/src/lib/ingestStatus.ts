/**
 * 取り込みバッチの鮮度・失敗状況を、トップ画面の更新状況バナー向けに翻訳する層。
 *
 * `has_history=false`（開発/fixture環境等でログが無い）は「異常」ではないため、
 * バナー自体を表示しない（visible=false）。
 */
import type { IngestStatus } from "@pci/api-client";

import { formatRaceDate, jyoName, raceNumber } from "./races";

export type IngestStatusTone = "ok" | "warning" | "error";

export interface IngestFailureMeta {
  label: string;
  timestamp: string;
  detail: string;
}

export interface IncompleteRaceMeta {
  raceKey: string;
  label: string;
  condition: string;
  href: string;
}

export interface MissingTrackConditionRaceMeta {
  raceKey: string;
  label: string;
  condition: string;
  href: string;
}

export interface IngestStatusMeta {
  visible: boolean;
  tone: IngestStatusTone;
  headline: string;
  detail: string;
  color: string;
  failures: IngestFailureMeta[];
  incompleteRaces: IncompleteRaceMeta[];
  missingTrackConditionRaces: MissingTrackConditionRaceMeta[];
  recoveryCommand: string | null;
  metadataRecoveryCommand: string | null;
}

const TONE_COLOR: Record<IngestStatusTone, string> = {
  ok: "#16a34a",
  warning: "#d97706",
  error: "#dc2626",
};

function formatTimestamp(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso);
  if (!match) return iso;
  const [, , month, day, hour, minute] = match;
  return `${Number(month)}/${Number(day)} ${hour}:${minute}`;
}

function buildFailures(status: IngestStatus): IngestFailureMeta[] {
  return status.recent_failures.map((f) => ({
    label: `${f.step}（${f.mode}）`,
    timestamp: formatTimestamp(f.started_at),
    detail: f.error_summary,
  }));
}

function buildIncompleteRaces(status: IngestStatus): IncompleteRaceMeta[] {
  return status.incomplete_races.map((race) => ({
    raceKey: race.race_key,
    label: `${formatRaceDate(race.race_date)} ${jyoName(race.jyo_cd)} ${raceNumber(race.race_key)}`,
    condition: `${race.track_type}${race.distance_m}m`,
    href: `/races/${race.race_key}/forecast`,
  }));
}

function buildMissingTrackConditionRaces(
  status: IngestStatus,
): MissingTrackConditionRaceMeta[] {
  return status.missing_track_condition_races.map((race) => ({
    raceKey: race.race_key,
    label: `${formatRaceDate(race.race_date)} ${jyoName(race.jyo_cd)} ${raceNumber(race.race_key)}`,
    condition: `${race.track_type}${race.distance_m}m`,
    href: `/races/${race.race_key}/pace-analysis`,
  }));
}

export function buildIngestRecoveryCommand(daysBack: number): string {
  const safeDaysBack = Math.max(10, Math.ceil(daysBack));
  return (
    "powershell -ExecutionPolicy Bypass -File " +
    `apps\\ingestion-worker\\scripts\\run_mykeibadb_full_sync.ps1 -DaysBack ${safeDaysBack}`
  );
}

export function buildRaceMetadataRecoveryCommand(
  dateFrom: string,
  dateTo: string,
): string {
  const compactFrom = dateFrom.replaceAll("-", "");
  const compactTo = dateTo.replaceAll("-", "");
  return (
    "powershell -ExecutionPolicy Bypass -File " +
    "apps\\ingestion-worker\\scripts\\run_batch.ps1 " +
    `-Step race-metadata -Mode mykeibadb -Date ${compactFrom} ` +
    `-DateTo ${compactTo} -ChunkDays 7`
  );
}

function recoveryCommand(status: IngestStatus): string {
  return buildIngestRecoveryCommand(status.recommended_sync_days_back);
}

function metadataRecoveryCommand(status: IngestStatus): string | null {
  if (!status.has_missing_track_conditions) return null;
  return buildRaceMetadataRecoveryCommand(
    status.race_metadata_date_from,
    status.race_metadata_date_to,
  );
}

const HIDDEN: IngestStatusMeta = {
  visible: false,
  tone: "ok",
  headline: "",
  detail: "",
  color: TONE_COLOR.ok,
  failures: [],
  incompleteRaces: [],
  missingTrackConditionRaces: [],
  recoveryCommand: null,
  metadataRecoveryCommand: null,
};

export function ingestStatusMeta(status: IngestStatus): IngestStatusMeta {
  if (
    !status.has_history &&
    !status.has_incomplete_races &&
    !status.has_missing_track_conditions
  ) {
    return HIDDEN;
  }

  if (status.last_attempt_failed) {
    return {
      visible: true,
      tone: "error",
      headline: "直近の取り込みに失敗しました",
      detail: status.last_success_at
        ? "直前の自動取り込みが失敗しています。次回の自動実行を待つか、手動同期をご検討ください。"
        : "取り込みがまだ一度も成功していません。手動同期をご検討ください。",
      color: TONE_COLOR.error,
      failures: buildFailures(status),
      incompleteRaces: buildIncompleteRaces(status),
      missingTrackConditionRaces: buildMissingTrackConditionRaces(status),
      recoveryCommand: recoveryCommand(status),
      metadataRecoveryCommand: metadataRecoveryCommand(status),
    };
  }

  if (status.has_incomplete_races) {
    return {
      visible: true,
      tone: "warning",
      headline: `成績未取込のレースが${status.incomplete_race_count}件あります`,
      detail: "開催済みですが出走前の状態で残っています。結果データの取り込み状況をご確認ください。",
      color: TONE_COLOR.warning,
      failures: buildFailures(status),
      incompleteRaces: buildIncompleteRaces(status),
      missingTrackConditionRaces: buildMissingTrackConditionRaces(status),
      recoveryCommand: recoveryCommand(status),
      metadataRecoveryCommand: metadataRecoveryCommand(status),
    };
  }

  if (status.has_missing_track_conditions) {
    return {
      visible: true,
      tone: "warning",
      headline: `馬場情報未反映の確定レースが${status.missing_track_condition_count}件あります`,
      detail:
        "直近1年の確定レースに馬場状態の欠損があります。欠損中は馬場補正と馬場別検証を利用できません。",
      color: TONE_COLOR.warning,
      failures: buildFailures(status),
      incompleteRaces: [],
      missingTrackConditionRaces: buildMissingTrackConditionRaces(status),
      recoveryCommand: null,
      metadataRecoveryCommand: metadataRecoveryCommand(status),
    };
  }

  if (status.is_stale) {
    const days = status.days_since_last_success;
    return {
      visible: true,
      tone: "warning",
      headline:
        days != null
          ? `データ更新が${days}日間確認できていません`
          : "データ更新の実績がまだ確認できていません",
      detail: "自動取り込みが止まっている可能性があります。手動同期をご検討ください。",
      color: TONE_COLOR.warning,
      failures: buildFailures(status),
      incompleteRaces: [],
      missingTrackConditionRaces: [],
      recoveryCommand: recoveryCommand(status),
      metadataRecoveryCommand: null,
    };
  }

  return {
    visible: true,
    tone: "ok",
    headline: "データは最新です",
    detail: "直近の自動取り込みは正常に完了しています。",
    color: TONE_COLOR.ok,
    failures: [],
    incompleteRaces: [],
    missingTrackConditionRaces: [],
    recoveryCommand: null,
    metadataRecoveryCommand: null,
  };
}
