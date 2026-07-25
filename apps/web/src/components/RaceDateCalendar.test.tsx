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
    expect(markup.match(/data-mobile-date-item/g)).toHaveLength(dates.length);
    expect(markup).toContain('aria-current="date"');
    expect(markup).toContain("7月25日（土）");
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
});
