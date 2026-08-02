import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { RaceDateCalendar } from "./RaceDateCalendar";

const dates = [
  "2026-07-04",
  "2026-07-05",
  "2026-07-11",
  "2026-07-12",
  "2026-07-18",
  "2026-07-19",
  "2026-07-25",
  "2026-07-26",
];

describe("RaceDateCalendar", () => {
  it("スマホでは開催日だけを日付ストリップへ表示する", () => {
    const markup = renderToStaticMarkup(
      <RaceDateCalendar
        dates={dates}
        selectedDate="2026-07-25"
        performanceDays={90}
      />,
    );

    expect(markup).toContain("data-mobile-date-calendar");
    expect(markup).toContain("data-mobile-date-strip");
    // 選択日(2026-07-25, index 6)の前4件+本人+後1件 = 6件（全8件は並べない）。
    expect(markup.match(/data-mobile-date-item/g)).toHaveLength(6);
    expect(markup).toContain('aria-current="date"');
    expect(markup).toContain("2026年7月25日（土）");
  });

  it("別の開催日へ期間条件を維持して遷移できる", () => {
    const markup = renderToStaticMarkup(
      <RaceDateCalendar
        dates={dates}
        selectedDate="2026-07-25"
        performanceDays={180}
      />,
    );

    expect(markup).toContain(
      'href="/?date=2026-07-26&amp;performance_days=180"',
    );
    expect(markup).toContain(
      'aria-label="2026年7月25日（選択中）"',
    );
  });

  it("開催日が多い場合でも日付ストリップは選択日周辺だけに絞る", () => {
    const manyDates = Array.from({ length: 40 }, (_, i) => {
      const d = new Date("2026-01-04T00:00:00");
      d.setDate(d.getDate() + i * 7);
      const mm = String(d.getMonth() + 1).padStart(2, "0");
      const dd = String(d.getDate()).padStart(2, "0");
      return `${d.getFullYear()}-${mm}-${dd}`;
    });

    const markup = renderToStaticMarkup(
      <RaceDateCalendar
        dates={manyDates}
        selectedDate={manyDates[20]}
        performanceDays={90}
      />,
    );

    expect(markup.match(/data-mobile-date-item/g)?.length ?? 0).toBeLessThan(
      manyDates.length,
    );
    expect(markup).toContain('aria-current="date"');
  });

  it("スマホでは月カレンダーを既定で閉じ、「他の日程を探す」で開ける", () => {
    const markup = renderToStaticMarkup(
      <RaceDateCalendar
        dates={dates}
        selectedDate="2026-07-25"
        performanceDays={90}
      />,
    );

    expect(markup).toContain("data-mobile-date-picker-toggle");
    expect(markup).toContain("他の日程を探す");
    expect(markup).toContain('aria-expanded="false"');
    expect(markup).toMatch(/data-mobile-date-picker="true" class="hidden /);
  });

  it("月カレンダーに年ジャンプの操作を追加する", () => {
    const markup = renderToStaticMarkup(
      <RaceDateCalendar
        dates={dates}
        selectedDate="2026-07-25"
        performanceDays={90}
      />,
    );

    expect(markup).toContain('aria-label="前年"');
    expect(markup).toContain('aria-label="翌年"');
    expect(markup).toContain('aria-label="前月"');
    expect(markup).toContain('aria-label="翌月"');
  });
});
