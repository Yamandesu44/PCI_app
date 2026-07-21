/**
 * 取り込みバッチの鮮度・失敗状況を、トップ画面の更新状況バナー向けに翻訳する層。
 *
 * `has_history=false`（開発/fixture環境等でログが無い）は「異常」ではないため、
 * バナー自体を表示しない（visible=false）。
 */
import type { IngestStatus } from "@pci/api-client";

export type IngestStatusTone = "ok" | "warning" | "error";

export interface IngestFailureMeta {
  label: string;
  timestamp: string;
  detail: string;
}

export interface IngestStatusMeta {
  visible: boolean;
  tone: IngestStatusTone;
  headline: string;
  detail: string;
  color: string;
  failures: IngestFailureMeta[];
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

const HIDDEN: IngestStatusMeta = {
  visible: false,
  tone: "ok",
  headline: "",
  detail: "",
  color: TONE_COLOR.ok,
  failures: [],
};

export function ingestStatusMeta(status: IngestStatus): IngestStatusMeta {
  if (!status.has_history) {
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
    };
  }

  return {
    visible: true,
    tone: "ok",
    headline: "データは最新です",
    detail: "直近の自動取り込みは正常に完了しています。",
    color: TONE_COLOR.ok,
    failures: [],
  };
}
