import Link from "next/link";
import type { ReactNode } from "react";
import {
  ArrowUpRight,
  BarChart3,
  CalendarDays,
  CheckCircle2,
  Gauge,
  ListFilter,
  Search,
} from "lucide-react";
import { IngestStatusBanner } from "@/components/IngestStatusBanner";
import { RaceDateCalendar } from "@/components/RaceDateCalendar";

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
import { ApiError, type Forecast, type IngestStatus, type RaceSummary } from "@pci/api-client";

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

async function loadRaces(date?: string): Promise<{ races: RaceSummary[]; error: string | null }> {
  try {
    const races = date != null
      ? await api.listRaces(undefined, date)
      : await api.listRaces(1000);
    return { races, error: null };
  } catch (err) {
    const detail =
      err instanceof ApiError ? `APIエラー (${err.status})` : "APIに接続できませんでした";
    return { races: [], error: detail };
  }
}

async function loadAllRaceDates(): Promise<string[]> {
  try {
    return await api.listRaceDates();
  } catch {
    return [];
  }
}

async function loadIngestStatus(): Promise<IngestStatus | null> {
  try {
    return await api.getIngestStatus();
  } catch {
    // 取得失敗時はバナーを出さない（ページ全体を壊さない）。
    return null;
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
    value: "border-amber-200 bg-amber-50 text-amber-800",
    caution: "border-violet-200 bg-violet-50 text-violet-700",
    normal: "border-slate-200 bg-slate-50 text-slate-500",
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
        "group grid grid-cols-[44px_minmax(0,1fr)_20px] gap-3 rounded-md border bg-white p-3.5 text-slate-950 transition-all",
        "hover:-translate-y-px hover:border-slate-400 hover:shadow-md",
        featured ? "border-emerald-200 shadow-sm" : "border-slate-200 shadow-sm",
      ].join(" ")}
      href={raceHref(race)}
    >
      <span
        className={[
          "flex h-10 w-10 items-center justify-center rounded-md text-sm font-bold text-white",
          tone === "confirmed" ? "bg-emerald-700" : "bg-blue-600",
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
      <ArrowUpRight
        className="mt-1 h-4 w-4 text-slate-300 transition group-hover:text-slate-700"
        aria-hidden
      />
    </Link>
  );
}

function StatTile({
  icon,
  label,
  value,
  tone,
}: {
  icon: ReactNode;
  label: string;
  value: string | number;
  tone: "emerald" | "blue" | "violet" | "amber";
}) {
  const toneClass = {
    emerald: "bg-emerald-50 text-emerald-700",
    blue: "bg-blue-50 text-blue-700",
    violet: "bg-violet-50 text-violet-700",
    amber: "bg-amber-50 text-amber-700",
  }[tone];

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <p className="m-0 text-xs font-semibold text-slate-500">{label}</p>
        <span className={`flex h-8 w-8 items-center justify-center rounded-md ${toneClass}`}>
          {icon}
        </span>
      </div>
      <p className="m-0 mt-3 text-3xl font-semibold tracking-normal text-slate-950">{value}</p>
    </div>
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
              className="border-t border-slate-300 pt-4"
            >
              <div className="mb-4 flex items-center justify-between gap-3">
                <h3 className="m-0 text-base font-semibold tracking-normal text-slate-950">
                  {formatRaceDate(dateGroup.raceDate)}
                </h3>
                <span className="text-xs font-semibold text-slate-500">
                  {dateGroup.venues.reduce((sum, venue) => sum + venue.items.length, 0)}R
                </span>
              </div>

              <div className="grid gap-3 lg:grid-cols-3">
                {dateGroup.venues.map((venueGroup) => (
                  <div key={venueGroup.jyoCd} className="min-w-0">
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
  const weekend = weekendRange();
  const today = todayKey();

  // カレンダー用の全開催日・取り込み状況は並列で取得する。
  const [allDates, ingestStatus] = await Promise.all([loadAllRaceDates(), loadIngestStatus()]);
  const selectedDate = selectRaceDate(allDates, params?.date, weekend);

  // 選択日のレースを取得（過去日付でも正確に取得できるよう日付指定フェッチを使う）。
  const { races, error } = await loadRaces(selectedDate ?? undefined);
  const sortedRaces = [...races].sort(compareRaceSummary);
  const dates = allDates.length > 0 ? allDates : raceDates(sortedRaces);
  const visibleRaces = sortedRaces;
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
  // 過去日付で status="entries" のまま（成績未取込）のレース。確定後・出走前いずれにも非表示になるため第4セクションで救済。
  const pastEntryItems = visibleItems.filter(
    ({ race }) =>
      race.race_date < today &&
      statusTone(race.status) !== "confirmed" &&
      !weekendItems.some((i) => i.race.race_key === race.race_key) &&
      !upcomingItems.some((i) => i.race.race_key === race.race_key),
  );
  const venueCount = new Set(visibleItems.map(({ race }) => race.jyo_cd)).size;

  return (
    <main className="mx-auto w-full max-w-7xl px-4 py-7 text-slate-950 sm:px-6 lg:px-8 lg:py-9">
      {ingestStatus ? <IngestStatusBanner status={ingestStatus} /> : null}

      <section className="mb-7 border-b border-slate-200 pb-6">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl">
            <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase text-emerald-700">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              Race intelligence
            </div>
            <h1 className="m-0 text-3xl font-semibold tracking-normal">レースボード</h1>
            <p className="m-0 mt-2 text-sm leading-6 text-slate-600">
              開催日と競馬場から、展開予想と確定後の振り返りへ移動できます。
            </p>
          </div>
          <nav className="inline-flex w-fit max-w-full flex-wrap gap-1 rounded-md border border-slate-200 bg-white p-1 shadow-sm" aria-label="レース一覧フィルター">
            <a className="rounded px-3 py-2 text-sm font-semibold text-slate-600 transition hover:bg-slate-100 hover:text-slate-950" href="#weekend">
              今週末 {weekendItems.length}
            </a>
            <a className="rounded px-3 py-2 text-sm font-semibold text-slate-600 transition hover:bg-slate-100 hover:text-slate-950" href="#upcoming">
              出走前 {upcomingItems.length}
            </a>
            <a className="rounded px-3 py-2 text-sm font-semibold text-slate-600 transition hover:bg-slate-100 hover:text-slate-950" href="#confirmed">
              確定後 {confirmedItems.length}
            </a>
            {pastEntryItems.length > 0 && (
              <a className="rounded bg-amber-50 px-3 py-2 text-sm font-semibold text-amber-700" href="#past-entries">
                成績未取込 {pastEntryItems.length}
              </a>
            )}
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
        <StatTile tone="emerald" icon={<CalendarDays className="h-4 w-4" />} label="今週末の予想対象" value={weekendItems.length} />
        <StatTile tone="blue" icon={<Search className="h-4 w-4" />} label="出走前" value={weekendItems.length + upcomingItems.length} />
        <StatTile tone="violet" icon={<CheckCircle2 className="h-4 w-4" />} label="確定後" value={confirmedItems.length} />
        <StatTile tone="amber" icon={<ListFilter className="h-4 w-4" />} label="開催場" value={venueCount} />
      </section>

      <div className="grid items-start gap-7 lg:grid-cols-[272px_minmax(0,1fr)]">
        <aside className="lg:sticky lg:top-24">
          <RaceDateCalendar dates={dates} selectedDate={selectedDate} />
        </aside>
        <div className="min-w-0 space-y-9">
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

        {pastEntryItems.length > 0 && (
          <RaceGroupedSection
            id="past-entries"
            title="成績未取込レース"
            description="出走表データあり・成績未取込。--step results を実行すると確定後に移動します"
            items={pastEntryItems}
          />
        )}
        </div>
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
