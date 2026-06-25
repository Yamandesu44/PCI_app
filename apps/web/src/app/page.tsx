import Link from "next/link";
import type { ReactNode } from "react";
import {
  BarChart3,
  CalendarDays,
  CheckCircle2,
  Gauge,
  ListFilter,
  Search,
} from "lucide-react";

import { api } from "@/lib/api";
import {
  confidenceInsight,
  paceSpeedFromIndex,
  raceSpotlight,
  sanitizeBeginnerComment,
  sortByPai,
  type RaceSpotlightTone,
} from "@/lib/pace";
import { isForecastRace, isRaceInRange, weekendRange } from "@/lib/raceSchedule";
import {
  compareRaceSummary,
  formatRaceDate,
  groupRacesByDateAndVenue,
  raceClassLabel,
  raceCondition,
  raceDates,
  raceHref,
  raceNumber,
  statusLabel,
  statusTone,
} from "@/lib/races";
import { ApiError, type Forecast, type RaceSummary } from "@pci/api-client";

// レース一覧は実行時にバックエンドへ問い合わせる（ビルド時フェッチを避ける）。
export const dynamic = "force-dynamic";

interface RaceListItem {
  race: RaceSummary;
  forecast: Forecast | null;
}

interface RaceVenueItemGroup {
  jyoCd: string;
  venueName: string;
  items: RaceListItem[];
}

interface RaceDateItemGroup {
  raceDate: string;
  venues: RaceVenueItemGroup[];
}

interface HomePageProps {
  searchParams?: Promise<{ date?: string }>;
}

async function loadRaces(): Promise<{ races: RaceSummary[]; error: string | null }> {
  try {
    return { races: await api.listRaces(1000), error: null };
  } catch (err) {
    const detail =
      err instanceof ApiError ? `APIエラー (${err.status})` : "APIに接続できませんでした";
    return { races: [], error: detail };
  }
}

async function enrichForecasts(
  races: RaceSummary[],
  shouldFetchForecast: (race: RaceSummary) => boolean,
): Promise<RaceListItem[]> {
  return Promise.all(
    races.map(async (race) => {
      if (!shouldFetchForecast(race)) {
        return { race, forecast: null };
      }

      try {
        return { race, forecast: await api.getForecast(race.race_key) };
      } catch {
        return { race, forecast: null };
      }
    }),
  );
}

function raceActionLabel(race: RaceSummary): string {
  return statusTone(race.status) === "confirmed" ? "ペース分析へ" : "展開予想へ";
}

function topHorseLabel(forecast: Forecast): string | null {
  const top = sortByPai(forecast.horses ?? [])[0];
  if (!top) return null;
  const name = top.horse_name ?? `${top.horse_no}番`;
  return `${name} / ${top.running_style}`;
}

function groupRaceItemsByDateAndVenue(items: RaceListItem[]): RaceDateItemGroup[] {
  const itemByRaceKey = new Map(items.map((item) => [item.race.race_key, item]));
  return groupRacesByDateAndVenue(items.map((item) => item.race)).map((dateGroup) => ({
    raceDate: dateGroup.raceDate,
    venues: dateGroup.venues.map((venueGroup) => ({
      jyoCd: venueGroup.jyoCd,
      venueName: venueGroup.venueName,
      items: venueGroup.races
        .map((race) => itemByRaceKey.get(race.race_key))
        .filter((item): item is RaceListItem => item !== undefined),
    })),
  }));
}

function selectRaceDate(dates: string[], requestedDate: string | undefined, weekend: { from: string; to: string }): string | null {
  if (requestedDate && dates.includes(requestedDate)) return requestedDate;
  const weekendDate = dates.find((date) => date >= weekend.from && date <= weekend.to);
  if (weekendDate) return weekendDate;
  const todayKey = new Date().toISOString().slice(0, 10);
  const upcomingDate = dates.find((date) => date >= todayKey);
  return upcomingDate ?? dates.at(-1) ?? null;
}

function todayKey(): string {
  const today = new Date();
  const year = today.getFullYear();
  const month = `${today.getMonth() + 1}`.padStart(2, "0");
  const date = `${today.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${date}`;
}

function spotlightClass(tone: RaceSpotlightTone): string {
  const classes: Record<RaceSpotlightTone, string> = {
    focus: "border-rose-200 bg-rose-50 text-rose-700",
    value: "border-amber-200 bg-amber-50 text-amber-700",
    caution: "border-slate-300 bg-slate-100 text-slate-700",
    normal: "border-slate-200 bg-white text-slate-500",
  };
  return classes[tone];
}

function RaceCompactRow({ item, featured = false }: { item: RaceListItem; featured?: boolean }) {
  const { race, forecast } = item;
  const tone = statusTone(race.status);
  const speed = forecast ? paceSpeedFromIndex(forecast.predicted_rpci) : null;
  const confidence = forecast ? confidenceInsight(forecast.confidence) : null;
  const topHorse = forecast ? topHorseLabel(forecast) : null;
  const headline = forecast?.comment?.headline ? sanitizeBeginnerComment(forecast.comment.headline) : null;
  const spotlight = forecast
    ? raceSpotlight({
        confidence: forecast.confidence,
        fieldSize: race.field_size,
        horses: forecast.horses ?? [],
      })
    : null;
  const showSpotlight = spotlight !== null && spotlight.tone !== "normal";

  return (
    <Link
      className={[
        "group grid grid-cols-[42px_1fr] gap-3 rounded-md border bg-white p-3 text-slate-950 shadow-sm transition",
        "hover:border-slate-400 hover:bg-slate-50",
        featured ? "border-slate-300" : "border-slate-200",
      ].join(" ")}
      href={raceHref(race)}
    >
      <span
        className={[
          "flex h-10 w-10 items-center justify-center rounded-md text-sm font-bold text-white",
          tone === "confirmed" ? "bg-emerald-600" : "bg-blue-600",
        ].join(" ")}
      >
        {raceNumber(race.race_key)}
      </span>

      <div className="min-w-0">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="m-0 truncate text-sm font-semibold leading-tight">
              {raceClassLabel(race)}
              <span className="ml-2 text-xs font-medium text-slate-500">{raceCondition(race)}</span>
            </p>
            <p className="m-0 mt-1 text-xs text-slate-500">
              {race.field_size}頭 ・ {raceActionLabel(race)}
            </p>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-1">
            <span
              className={[
                "rounded-full border px-2 py-0.5 text-xs font-semibold",
                tone === "confirmed"
                  ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                  : "border-sky-200 bg-sky-50 text-sky-700",
              ].join(" ")}
            >
              {statusLabel(race.status)}
            </span>
            {showSpotlight ? (
              <span
                className={[
                  "rounded-full border px-2 py-0.5 text-xs font-semibold",
                  spotlightClass(spotlight.tone),
                ].join(" ")}
              >
                {spotlight.label}
              </span>
            ) : null}
          </div>
        </div>

        {forecast && speed ? (
          <div className="mt-2 grid gap-1 text-xs text-slate-600">
            <div className="flex flex-wrap gap-x-3 gap-y-1">
              <span>
                展開: <span className="font-semibold text-slate-950">{speed.beginnerLabel}</span>
              </span>
              <span>
                信頼度: <span className="font-semibold text-slate-950">{confidence?.label}</span>
              </span>
            </div>
            {topHorse ? <span className="truncate">候補: {topHorse}</span> : null}
            {showSpotlight ? <span className="truncate text-slate-500">{spotlight.reason}</span> : null}
            {headline ? <span className="truncate text-slate-500">{headline}</span> : null}
          </div>
        ) : (
          <p className="m-0 mt-2 text-xs text-slate-500">
            {tone === "confirmed"
              ? "確定後の流れと各馬の走りを確認できます。"
              : "出走馬データがそろうと展開プレビューを表示します。"}
          </p>
        )}
      </div>
    </Link>
  );
}

function StatTile({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string | number;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <p className="m-0 text-sm font-medium text-slate-500">{label}</p>
        <span className="text-slate-400">{icon}</span>
      </div>
      <p className="m-0 mt-2 text-2xl font-semibold tracking-normal text-slate-950">{value}</p>
    </div>
  );
}

function RaceDateTabs({ dates, selectedDate }: { dates: string[]; selectedDate: string | null }) {
  if (dates.length === 0) return null;

  return (
    <nav
      className="mb-8 flex gap-2 overflow-x-auto rounded-lg border border-slate-200 bg-white p-2 shadow-sm"
      aria-label="開催日を選択"
    >
      {dates.map((date) => {
        const selected = date === selectedDate;
        return (
          <Link
            key={date}
            href={`/?date=${date}`}
            className={[
              "shrink-0 rounded-md border px-4 py-2 text-sm font-semibold transition",
              selected
                ? "border-slate-950 bg-slate-950 text-white"
                : "border-slate-200 bg-white text-slate-700 hover:border-slate-400",
            ].join(" ")}
            aria-current={selected ? "page" : undefined}
          >
            {formatRaceDate(date)}
          </Link>
        );
      })}
    </nav>
  );
}

function RaceGroupedSection({
  id,
  title,
  description,
  items,
  featured = false,
}: {
  id: string;
  title: string;
  description: string;
  items: RaceListItem[];
  featured?: boolean;
}) {
  const dateGroups = groupRaceItemsByDateAndVenue(items);

  return (
    <section id={id} className="scroll-mt-5">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="m-0 text-lg font-semibold tracking-normal text-slate-950">{title}</h2>
          <p className="m-0 mt-1 text-sm text-slate-500">{description}</p>
        </div>
        <span className="text-sm font-medium text-slate-500">{items.length}件</span>
      </div>

      {items.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-300 bg-white p-5 text-sm text-slate-500">
          表示できるレースがありません。
        </p>
      ) : (
        <div className="space-y-4">
          {dateGroups.map((dateGroup) => (
            <section
              key={dateGroup.raceDate}
              className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
            >
              <div className="mb-3 flex items-center justify-between gap-3 border-b border-slate-100 pb-3">
                <h3 className="m-0 text-base font-semibold tracking-normal text-slate-950">
                  {formatRaceDate(dateGroup.raceDate)}
                </h3>
                <span className="text-xs font-semibold text-slate-500">
                  {dateGroup.venues.reduce((sum, venue) => sum + venue.items.length, 0)}R
                </span>
              </div>

              <div className="grid gap-3 lg:grid-cols-3">
                {dateGroup.venues.map((venueGroup) => (
                  <div key={venueGroup.jyoCd} className="min-w-0 rounded-lg bg-slate-50 p-3">
                    <div className="mb-3 flex items-center justify-between gap-2">
                      <h4 className="m-0 text-sm font-semibold text-slate-900">
                        {venueGroup.venueName}
                      </h4>
                      <span className="text-xs font-medium text-slate-500">
                        {venueGroup.items.length}件
                      </span>
                    </div>
                    <div className="grid gap-2">
                      {venueGroup.items.map((item) => (
                        <RaceCompactRow key={item.race.race_key} item={item} featured={featured} />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </section>
  );
}

export default async function HomePage({ searchParams }: HomePageProps) {
  const params = await searchParams;
  const { races, error } = await loadRaces();
  const sortedRaces = [...races].sort(compareRaceSummary);
  const weekend = weekendRange();
  const today = todayKey();
  const dates = raceDates(sortedRaces);
  const selectedDate = selectRaceDate(dates, params?.date, weekend);
  const visibleRaces = selectedDate
    ? sortedRaces.filter((race) => race.race_date === selectedDate)
    : sortedRaces;
  const visibleItems = error
    ? []
    : await enrichForecasts(
        visibleRaces,
        (race) => isForecastRace(race) && race.race_date >= today,
      );

  const weekendItems = visibleItems.filter(
    ({ race }) => isForecastRace(race) && isRaceInRange(race, weekend),
  );
  const upcomingItems = visibleItems.filter(
    ({ race }) =>
      isForecastRace(race) &&
      race.race_date >= today &&
      !weekendItems.some((item) => item.race.race_key === race.race_key),
  );
  const confirmedItems = visibleItems.filter(({ race }) => statusTone(race.status) === "confirmed");
  const venueCount = new Set(visibleItems.map(({ race }) => race.jyo_cd)).size;

  return (
    <main className="mx-auto max-w-6xl px-5 py-6 text-slate-950">
      <section className="mb-6 rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl">
            <p className="m-0 text-sm font-semibold text-slate-500">Race Board</p>
            <h1 className="m-0 mt-2 text-2xl font-semibold tracking-normal">レース一覧</h1>
            <p className="m-0 mt-2 text-sm leading-6 text-slate-600">
              開催日を選んで、競馬場ごとにレースを確認できます。
            </p>
          </div>
          <nav className="flex flex-wrap gap-2" aria-label="レース一覧フィルター">
            <a className="rounded-md border border-slate-200 px-3 py-2 text-sm font-semibold" href="#weekend">
              今週末 {weekendItems.length}
            </a>
            <a className="rounded-md border border-slate-200 px-3 py-2 text-sm font-semibold" href="#upcoming">
              出走前 {upcomingItems.length}
            </a>
            <a className="rounded-md border border-slate-200 px-3 py-2 text-sm font-semibold" href="#confirmed">
              確定後 {confirmedItems.length}
            </a>
          </nav>
        </div>
      </section>

      {error ? (
        <p className="mb-6 rounded-lg border border-dashed border-slate-300 bg-white p-5 text-sm text-slate-600">
          レース一覧を取得できませんでした（{error}）。
          <br />
          FastAPI バックエンド（<code>API_BASE_URL</code>）が起動しているか確認してください。
        </p>
      ) : null}

      <section className="mb-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile icon={<CalendarDays className="h-4 w-4" />} label="今週末の予想対象" value={weekendItems.length} />
        <StatTile icon={<Search className="h-4 w-4" />} label="出走前" value={weekendItems.length + upcomingItems.length} />
        <StatTile icon={<CheckCircle2 className="h-4 w-4" />} label="確定後" value={confirmedItems.length} />
        <StatTile icon={<ListFilter className="h-4 w-4" />} label="開催場" value={venueCount} />
      </section>

      <RaceDateTabs dates={dates} selectedDate={selectedDate} />

      <div className="space-y-9">
        <RaceGroupedSection
          id="weekend"
          title="今週末の予想対象"
          description={`${formatRaceDate(weekend.from)} - ${formatRaceDate(weekend.to)} の出走前レース`}
          items={weekendItems}
          featured
        />

        <RaceGroupedSection
          id="upcoming"
          title="その他の出走前レース"
          description="展開予想を確認できる未確定レース"
          items={upcomingItems}
        />

        <RaceGroupedSection
          id="confirmed"
          title="確定後レース"
          description="ペース分析と回顧コメントを確認できるレース"
          items={confirmedItems}
        />
      </div>

      <div className="mt-8 flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
        <Gauge className="h-4 w-4 text-slate-400" aria-hidden />
        <span>展開プレビューは出走馬データがあるレースに表示されます。</span>
        <BarChart3 className="h-4 w-4 text-slate-400" aria-hidden />
        <span>確定後はペース分析画面へ遷移します。</span>
      </div>
    </main>
  );
}
