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
        operator
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
    expect(markup).toContain("flex min-h-11 items-center justify-between");
    expect(markup).toContain("break-words");
    expect(markup).not.toContain("break-all");
    expect(markup).toContain('<p id="ingest-failures-heading"');
    expect(markup).toContain('<p id="incomplete-races-heading"');
    expect(markup).not.toContain('<h3 id="ingest-failures-heading"');
  });

  it("正常時は不要な詳細開閉を表示しない", () => {
    const markup = renderToStaticMarkup(
      <IngestStatusBanner operator status={status()} />,
    );

    expect(markup).not.toContain("<details");
    expect(markup).toContain("データは最新です");
    expect(markup).toContain("正常");
  });

  it("スマホでは状態と件数を要約し、詳細は任意展開に残す", () => {
    const markup = renderToStaticMarkup(
      <IngestStatusBanner
        operator
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

  it("モバイル専用の要約行に見出しを常時表示し、detail文は含めない", () => {
    const markup = renderToStaticMarkup(
      <IngestStatusBanner
        operator
        status={status({
          has_incomplete_races: true,
          incomplete_race_count: 3,
          incomplete_races: [],
        })}
      />,
    );

    const mobileMatch =
      /<div class="flex items-center gap-2 md:hidden">[\s\S]*?<\/div>/.exec(
        markup,
      );
    expect(mobileMatch).not.toBeNull();
    const mobileSummary = mobileMatch![0];
    expect(mobileSummary).toContain("成績未取込のレースが3件あります");
    expect(mobileSummary).not.toContain(
      "開催済みですが出走前の状態で残っています",
    );
  });

  it("PC表示（md:）は見出し・detail文とも従来どおり維持する", () => {
    const markup = renderToStaticMarkup(
      <IngestStatusBanner
        operator
        status={status({
          has_incomplete_races: true,
          incomplete_race_count: 3,
          incomplete_races: [],
        })}
      />,
    );

    expect(markup).toContain('class="hidden items-start gap-3 md:flex"');
    const desktopMatch =
      /<div class="hidden items-start gap-3 md:flex">[\s\S]*?<\/div><\/div>/.exec(
        markup,
      );
    expect(desktopMatch).not.toBeNull();
    const desktopBlock = desktopMatch![0];
    expect(desktopBlock).toContain("成績未取込のレースが3件あります");
    expect(desktopBlock).toContain("開催済みですが出走前の状態で残っています");
  });

  describe("訪問者向け（operator 未指定）", () => {
    const failing = {
      last_attempt_failed: true,
      recent_failures: [
        {
          batch_date: "2026-08-07",
          step: "forecasts",
          mode: "mykeibadb",
          started_at: "2026-08-07T12:03:00+09:00",
          error_summary:
            "Ingest API エラー 504 /internal/ingest/forecasts/precompute: upstream request timeout",
        },
      ],
    };

    it("内部の事情を出さない", () => {
      // 公開画面に出ていたもの: 内部エンドポイントのパス、例外文言、
      // そして訪問者には実行できない PowerShell の再同期コマンド。
      const markup = renderToStaticMarkup(
        <IngestStatusBanner status={status(failing)} />,
      );

      expect(markup).not.toContain("/internal/ingest");
      expect(markup).not.toContain("upstream request timeout");
      expect(markup).not.toContain("powershell");
      expect(markup).not.toContain("詳細と復旧手順");
      expect(markup).not.toContain("手動同期");
    });

    it("異常であること自体は伝える", () => {
      // 隠すのは手順であって状態ではない。
      const markup = renderToStaticMarkup(
        <IngestStatusBanner status={status(failing)} />,
      );

      expect(markup).toContain("データの更新が遅れています");
      expect(markup).toContain("最新でない可能性");
    });

    it("運用者にだけ詳細を見せる", () => {
      const markup = renderToStaticMarkup(
        <IngestStatusBanner operator status={status(failing)} />,
      );

      expect(markup).toContain("詳細と復旧手順");
      expect(markup).toContain("/internal/ingest");
    });
  });
});
