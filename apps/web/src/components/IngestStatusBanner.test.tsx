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
  });

  it("正常時は不要な詳細開閉を表示しない", () => {
    const markup = renderToStaticMarkup(<IngestStatusBanner status={status()} />);

    expect(markup).not.toContain("<details");
    expect(markup).toContain("データは最新です");
  });
});
