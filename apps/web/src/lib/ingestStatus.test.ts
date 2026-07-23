import { describe, expect, it } from "vitest";

import { ingestStatusMeta } from "./ingestStatus";
import type { IngestStatus } from "@pci/api-client";

function status(overrides: Partial<IngestStatus>): IngestStatus {
  return {
    has_history: true,
    last_success_at: null,
    last_success_step: null,
    last_attempt_failed: false,
    days_since_last_success: null,
    is_stale: false,
    recent_failures: [],
    has_incomplete_races: false,
    incomplete_race_count: 0,
    recommended_sync_days_back: 10,
    incomplete_races: [],
    race_metadata_date_from: "2025-07-22",
    race_metadata_date_to: "2026-07-22",
    has_missing_track_conditions: false,
    missing_track_condition_count: 0,
    missing_track_condition_races: [],
    ...overrides,
  };
}

describe("ingestStatusMeta", () => {
  it("履歴が無い場合はバナー自体を非表示にする", () => {
    const meta = ingestStatusMeta(status({ has_history: false }));
    expect(meta.visible).toBe(false);
  });

  it("履歴が無くても成績未取込レースがあれば警告する", () => {
    const meta = ingestStatusMeta(
      status({
        has_history: false,
        has_incomplete_races: true,
        incomplete_race_count: 1,
        incomplete_races: [
          {
            race_key: "2026072005010111",
            race_date: "2026-07-20",
            jyo_cd: "05",
            track_type: "芝",
            distance_m: 1600,
          },
        ],
      }),
    );
    expect(meta.visible).toBe(true);
    expect(meta.tone).toBe("warning");
    expect(meta.headline).toContain("1件");
    expect(meta.incompleteRaces).toEqual([
      {
        raceKey: "2026072005010111",
        label: "7月20日 東京 11R",
        condition: "芝1600m",
        href: "/races/2026072005010111/forecast",
      },
    ]);
    expect(meta.recoveryCommand).toContain("-DaysBack 10");
  });

  it("正常時は ok トーンで、失敗一覧を出さない", () => {
    const meta = ingestStatusMeta(
      status({ is_stale: false, last_attempt_failed: false, days_since_last_success: 0 }),
    );
    expect(meta.visible).toBe(true);
    expect(meta.tone).toBe("ok");
    expect(meta.headline).toContain("最新");
    expect(meta.failures).toEqual([]);
    expect(meta.recoveryCommand).toBeNull();
  });

  it("直近の取り込みが失敗していれば error トーンにする", () => {
    const meta = ingestStatusMeta(
      status({
        last_attempt_failed: true,
        is_stale: false,
        recent_failures: [
          {
            batch_date: "2026-07-12",
            step: "entries",
            mode: "mykeibadb",
            started_at: "2026-07-12T07:00:00+00:00",
            error_summary: "connection timeout",
          },
        ],
      }),
    );
    expect(meta.tone).toBe("error");
    expect(meta.headline).toContain("失敗");
    expect(meta.failures).toEqual([
      { label: "entries（mykeibadb）", timestamp: "7/12 07:00", detail: "connection timeout" },
    ]);
  });

  it("失敗はないが鮮度が古い場合は warning トーンにし、経過日数を明記する", () => {
    const meta = ingestStatusMeta(
      status({ is_stale: true, last_attempt_failed: false, days_since_last_success: 6 }),
    );
    expect(meta.tone).toBe("warning");
    expect(meta.headline).toContain("6日間");
  });

  it("一度も成功していない場合は経過日数なしの警告文言にする", () => {
    const meta = ingestStatusMeta(
      status({ is_stale: true, last_attempt_failed: false, days_since_last_success: null }),
    );
    expect(meta.tone).toBe("warning");
    expect(meta.headline).not.toMatch(/\d+日間/);
  });

  it("失敗中でも直近成功があれば「再試行を待つ」旨の文言にする", () => {
    const withPriorSuccess = ingestStatusMeta(
      status({ last_attempt_failed: true, last_success_at: "2026-07-11T18:00:00+00:00" }),
    );
    expect(withPriorSuccess.detail).toContain("次回の自動実行");

    const neverSucceeded = ingestStatusMeta(
      status({ last_attempt_failed: true, last_success_at: null }),
    );
    expect(neverSucceeded.detail).toContain("一度も成功していません");
  });

  it("最古の未取込レースを含む遡及日数で再同期コマンドを作る", () => {
    const meta = ingestStatusMeta(
      status({
        has_incomplete_races: true,
        incomplete_race_count: 25,
        recommended_sync_days_back: 32,
      }),
    );

    expect(meta.recoveryCommand).toBe(
      "powershell -ExecutionPolicy Bypass -File " +
        "apps\\ingestion-worker\\scripts\\run_mykeibadb_full_sync.ps1 -DaysBack 32",
    );
  });

  it("馬場状態が欠けた確定レースを専用警告として表示する", () => {
    const meta = ingestStatusMeta(
      status({
        has_missing_track_conditions: true,
        missing_track_condition_count: 1,
        missing_track_condition_races: [
          {
            race_key: "2026072005010111",
            race_date: "2026-07-20",
            jyo_cd: "05",
            track_type: "芝",
            distance_m: 1600,
          },
        ],
      }),
    );

    expect(meta.visible).toBe(true);
    expect(meta.tone).toBe("warning");
    expect(meta.headline).toContain("馬場情報未反映");
    expect(meta.missingTrackConditionRaces).toEqual([
      {
        raceKey: "2026072005010111",
        label: "7月20日 東京 11R",
        condition: "芝1600m",
        href: "/races/2026072005010111/pace-analysis",
      },
    ]);
    expect(meta.metadataRecoveryCommand).toBe(
      "powershell -ExecutionPolicy Bypass -File " +
        "apps\\ingestion-worker\\scripts\\run_batch.ps1 " +
        "-Step race-metadata -Mode mykeibadb -Date 20250722 " +
        "-DateTo 20260722 -ChunkDays 7",
    );
    expect(meta.recoveryCommand).toBeNull();
  });

  it("履歴が無くても馬場状態の欠損があれば警告する", () => {
    const meta = ingestStatusMeta(
      status({
        has_history: false,
        has_missing_track_conditions: true,
        missing_track_condition_count: 3,
      }),
    );

    expect(meta.visible).toBe(true);
    expect(meta.headline).toContain("3件");
  });
});
