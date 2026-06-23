import { describe, expect, it } from "vitest";

import { isForecastRace, isRaceInRange, weekendRange } from "./raceSchedule";

describe("weekendRange", () => {
  it("平日は直近の土日を返す", () => {
    expect(weekendRange(new Date(2026, 5, 23))).toEqual({
      from: "2026-06-27",
      to: "2026-06-28",
    });
  });

  it("土曜日は当日から日曜日までを返す", () => {
    expect(weekendRange(new Date(2026, 5, 27))).toEqual({
      from: "2026-06-27",
      to: "2026-06-28",
    });
  });

  it("日曜日は前日の土曜日から当日までを返す", () => {
    expect(weekendRange(new Date(2026, 5, 28))).toEqual({
      from: "2026-06-27",
      to: "2026-06-28",
    });
  });
});

describe("race schedule filters", () => {
  it("期間内のレースだけを判定する", () => {
    const range = { from: "2026-06-27", to: "2026-06-28" };
    expect(isRaceInRange({ race_date: "2026-06-27" }, range)).toBe(true);
    expect(isRaceInRange({ race_date: "2026-06-29" }, range)).toBe(false);
  });

  it("出走前レースを予想対象として扱う", () => {
    expect(isForecastRace({ status: "entries" })).toBe(true);
    expect(isForecastRace({ status: "result" })).toBe(false);
  });
});
