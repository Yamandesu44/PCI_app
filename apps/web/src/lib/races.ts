/**
 * レース一覧表示のための純粋プレゼンテーションロジック。
 *
 * 競馬場コード→名称の変換や、レース状態に応じた遷移先（展開予想／ペース分析）の
 * 決定など、副作用のない決定的な変換のみを担う。vitest で単体テストする。
 */
import type { RaceSummary } from "@pci/api-client";

// JRA 中央競馬場コード（2桁）→ 競馬場名。取り込みスコープは中央のみ（CLAUDE.md）。
const JYO_NAMES: Record<string, string> = {
  "01": "札幌",
  "02": "函館",
  "03": "福島",
  "04": "新潟",
  "05": "東京",
  "06": "中山",
  "07": "中京",
  "08": "京都",
  "09": "阪神",
  "10": "小倉",
};

/** 競馬場コードを名称へ。未知コードはコードをそのまま返す。 */
export function jyoName(jyoCd: string): string {
  return JYO_NAMES[jyoCd] ?? jyoCd;
}

export type RaceStatusTone = "upcoming" | "confirmed";

/** レース状態（entries/result）を表示用トーンへ。 */
export function statusTone(status: string): RaceStatusTone {
  return status === "result" ? "confirmed" : "upcoming";
}

/** 状態に応じた日本語ラベル。 */
export function statusLabel(status: string): string {
  return statusTone(status) === "confirmed" ? "確定後" : "出走前";
}

/**
 * レースの遷移先を状態から決定する。
 *   出走前（entries） → 展開予想（forecast）
 *   確定後（result）  → ペース分析（pace-analysis）
 */
export function raceHref(race: Pick<RaceSummary, "race_key" | "status">): string {
  const sub = statusTone(race.status) === "confirmed" ? "pace-analysis" : "forecast";
  return `/races/${race.race_key}/${sub}`;
}

/** RaceKey 16桁から「R」付きレース番号を取り出す（末尾2桁）。不正長はそのまま。 */
export function raceNumber(raceKey: string): string {
  if (raceKey.length !== 16) return raceKey;
  return `${Number(raceKey.slice(14, 16))}R`;
}

/** ISO 日付文字列（YYYY-MM-DD）を「M月D日」へ。不正値はそのまま返す。 */
export function formatRaceDate(isoDate: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate);
  if (!m) return isoDate;
  return `${Number(m[2])}月${Number(m[3])}日`;
}

/** 一覧の見出しに使う1行サマリ（例: 「東京 11R ・ 芝1600m」）。 */
export function raceTitle(race: RaceSummary): string {
  return `${jyoName(race.jyo_cd)} ${raceNumber(race.race_key)} ・ ${race.track_type}${race.distance_m}m`;
}

/** コース条件を短く表示する。 */
export function raceCondition(race: Pick<RaceSummary, "track_type" | "distance_m">): string {
  return `${race.track_type}${race.distance_m}m`;
}

/** グレード・クラスを一覧用のラベルへ。未設定時は一般戦として扱う。 */
export function raceClassLabel(race: Pick<RaceSummary, "grade" | "race_class">): string {
  const name = normalizeRaceClass(race.race_class);
  const grade = normalizeRaceClass(race.grade);
  return name || grade || "一般";
}

/** レース名が欠損・プレースホルダーなら、競馬場とR番号へフォールバックする。 */
export function raceNameOrFallback(
  race: Pick<RaceSummary, "race_key" | "jyo_cd" | "race_class">,
): string {
  return (
    normalizeRaceClass(race.race_class) ??
    `${jyoName(race.jyo_cd)} ${raceNumber(race.race_key)}`
  );
}

function normalizeRaceClass(value: string | null | undefined): string | null {
  const name = value?.replace(/\s*特別登録$/, "").trim();
  if (!name) return null;
  if (new Set(["@", "＠", "...", "…", "-", "－"]).has(name)) return null;
  // DB内の固定長パディング残留: "@縲縲縲..." のように先頭が @ の場合もプレースホルダ
  if (name.startsWith("@") || name.startsWith("＠")) return null;
  return name;
}

/** レース番号を数値化する。一覧ソート用なので、不正値は最後に寄せる。 */
export function raceNumberValue(raceKey: string): number {
  if (raceKey.length !== 16) return 999;
  const value = Number(raceKey.slice(14, 16));
  return Number.isFinite(value) ? value : 999;
}

/** 開催日・競馬場・レース番号の順で並べるための比較関数。 */
export function compareRaceSummary(a: RaceSummary, b: RaceSummary): number {
  return (
    a.race_date.localeCompare(b.race_date) ||
    a.jyo_cd.localeCompare(b.jyo_cd) ||
    raceNumberValue(a.race_key) - raceNumberValue(b.race_key)
  );
}

export interface RaceVenueGroup {
  jyoCd: string;
  venueName: string;
  races: RaceSummary[];
}

export interface RaceDateGroup {
  raceDate: string;
  venues: RaceVenueGroup[];
}

/** レース一覧を netkeiba 風に「日付 → 競馬場 → レース順」でまとめる。 */
export function groupRacesByDateAndVenue(races: RaceSummary[]): RaceDateGroup[] {
  const sorted = [...races].sort(compareRaceSummary);
  const dateGroups = new Map<string, Map<string, RaceSummary[]>>();

  for (const race of sorted) {
    const venueGroups = dateGroups.get(race.race_date) ?? new Map<string, RaceSummary[]>();
    const venueRaces = venueGroups.get(race.jyo_cd) ?? [];
    venueRaces.push(race);
    venueGroups.set(race.jyo_cd, venueRaces);
    dateGroups.set(race.race_date, venueGroups);
  }

  return [...dateGroups.entries()].map(([raceDate, venueGroups]) => ({
    raceDate,
    venues: [...venueGroups.entries()].map(([jyoCd, venueRaces]) => ({
      jyoCd,
      venueName: jyoName(jyoCd),
      races: venueRaces,
    })),
  }));
}

/** レース一覧に含まれる開催日を昇順で返す。 */
export function raceDates(races: Pick<RaceSummary, "race_date">[]): string[] {
  return [...new Set(races.map((race) => race.race_date))].sort();
}
