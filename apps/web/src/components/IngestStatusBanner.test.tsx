import type { IngestStatus } from "@pci/api-client";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { IngestStatusBanner } from "./IngestStatusBanner";

function status(overrides: Partial<IngestStatus> = {}): IngestStatus {
  return {
    has_history: true,
    last_success_at: "2026-07-23T18:00:00+09:00",
    last_success_step: "results",
    last_attempt_failed: false,
    days_since_last_success: 1,
    is_stale: false,
    recent_failures: [],
    has_incomplete_races: false,
    incomplete_race_count: 0,
    recommended_sync_days_back: 10,
    incomplete_races: [],
    race_metadata_date_from: "2025-07-24",
    race_metadata_date_to: "2026-07-24",
    has_missing_track_conditions: false,
    missing_track_condition_count: 0,
    missing_track_condition_races: [],
    has_duplicate_races: false,
    duplicate_race_group_count: 0,
    duplicate_race_groups: [],
    ...overrides,
  };
}

describe("IngestStatusBanner", () => {
  it("警告の詳細と復旧手順を1つの折りたたみにまとめる", () => {
    const markup = renderToStaticMarkup(
      <IngestStatusBanner
        status={status({
          last_attempt_failed: true,
          recent_failures: [
            {
              batch_date: "2026-07-23",
              step: "results",
              mode: "mykeibadb",
              started_at: "2026-07-23T18:30:00+09:00",
              error_summary:
                "Ingest API エラー 500 /internal/ingest/results: Internal Server Error",
            },
          ],
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
        })}
      />,
    );

    expect(markup.match(/<details/g)).toHaveLength(1);
    expect(markup).not.toContain("<details open");
    expect(markup).toContain("詳細と復旧手順");
    expect(markup).toContain("成績未取込の対象");
    expect(markup).toContain("再同期コマンド");
    expect(markup).toContain("break-words");
    expect(markup).not.toContain("break-all");
  });

  it("正常時は不要な詳細開閉を表示しない", () => {
    const markup = renderToStaticMarkup(<IngestStatusBanner status={status()} />);

    expect(markup).not.toContain("<details");
    expect(markup).toContain("データは最新です");
    expect(markup).toContain("正常");
  });

  it("スマホでは状態と件数を要約し、詳細は任意展開に残す", () => {
    const markup = renderToStaticMarkup(
      <IngestStatusBanner
        status={status({
          last_attempt_failed: true,
          has_incomplete_races: true,
          incomplete_race_count: 3,
          has_missing_track_conditions: true,
          missing_track_condition_count: 2,
          has_duplicate_races: true,
          duplicate_race_group_count: 1,
          recent_failures: [
            {
              batch_date: "2026-07-23",
              step: "results",
              mode: "mykeibadb",
              started_at: "2026-07-23T18:30:00+09:00",
              error_summary: "結果の送信に失敗しました",
            },
          ],
        })}
      />,
    );

    expect(markup).toContain("data-mobile-ingest-summary");
    expect(markup).toContain("要対応");
    expect(markup).toContain("直近失敗");
    expect(markup).toContain("成績未取込 3件");
    expect(markup).toContain("馬場情報 2件");
    expect(markup).toContain("重複 1組");
    expect(markup).toContain("詳細を確認");
    expect(markup).toContain("詳細と復旧手順");
    expect(markup).toContain("max-md:hidden");
  });
});
