import type { RaceSummary } from "@pci/api-client";

import { statusTone } from "./races";

function toDateKey(date: Date): string {
  const y = date.getFullYear();
  const m = `${date.getMonth() + 1}`.padStart(2, "0");
  const d = `${date.getDate()}`.padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function addDays(date: Date, days: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

/** 今日を基準に、直近の土日を「今週末」として返す。土日は当日を含める。 */
export function weekendRange(base = new Date()): { from: string; to: string } {
  const day = base.getDay();
  const daysToSaturday = day === 0 ? -1 : day === 6 ? 0 : 6 - day;
  const saturday = addDays(base, daysToSaturday);
  const sunday = addDays(saturday, 1);
  return { from: toDateKey(saturday), to: toDateKey(sunday) };
}

export function isRaceInRange(
  race: Pick<RaceSummary, "race_date">,
  range: { from: string; to: string },
): boolean {
  return race.race_date >= range.from && race.race_date <= range.to;
}

export function isForecastRace(race: Pick<RaceSummary, "status">): boolean {
  return statusTone(race.status) === "upcoming";
}
