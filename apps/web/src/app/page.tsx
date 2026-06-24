import Link from "next/link";
import type { ReactNode } from "react";
import {
  ArrowRight,
  BarChart3,
  CalendarDays,
  CheckCircle2,
  Gauge,
  ListFilter,
  Search,
} from "lucide-react";

import { api } from "@/lib/api";
import { confidenceInsight, paceSpeedFromIndex, sanitizeBeginnerComment, sortByPai } from "@/lib/pace";
import { isForecastRace, isRaceInRange, weekendRange } from "@/lib/raceSchedule";
import {
  compareRaceSummary,
  formatRaceDate,
  jyoName,
  raceClassLabel,
  raceCondition,
  raceHref,
  raceNumber,
  raceTitle,
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

async function loadRaces(): Promise<{ races: RaceSummary[]; error: string | null }> {
  try {
    return { races: await api.listRaces(100), error: null };
  } catch (err) {
    const detail =
      err instanceof ApiError ? `APIエラー (${err.status})` : "APIに接続できませんでした";
    return { races: [], error: detail };
  }
}

async function enrichForecasts(races: RaceSummary[]): Promise<RaceListItem[]> {
  return Promise.all(
    races.map(async (race) => {
      if (!isForecastRace(race)) {
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

function RaceCard({ item, featured = false }: { item: RaceListItem; featured?: boolean }) {
  const { race, forecast } = item;
  const tone = statusTone(race.status);
  const speed = forecast ? paceSpeedFromIndex(forecast.predicted_rpci) : null;
  const confidence = forecast ? confidenceInsight(forecast.confidence) : null;
  const topHorse = forecast ? topHorseLabel(forecast) : null;
  const headline = forecast?.comment?.headline
    ? sanitizeBeginnerComment(forecast.comment.headline)
    : speed?.beginnerSummary;

  return (
    <Link
      className={[
        "group flex h-full flex-col rounded-lg border bg-white p-4 text-slate-950 shadow-sm transition",
        "hover:-translate-y-0.5 hover:border-slate-400 hover:shadow-md",
        featured ? "border-slate-900" : "border-slate-200",
      ].join(" ")}
      href={raceHref(race)}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="m-0 text-xs font-semibold text-slate-500">
            {formatRaceDate(race.race_date)} ・ {jyoName(race.jyo_cd)}
          </p>
          <h2 className="m-0 mt-1 text-base font-semibold leading-tight tracking-normal">
            {raceNumber(race.race_key)} ・ {raceCondition(race)}
          </h2>
        </div>
        <span
          className={[
            "shrink-0 rounded-full border px-2.5 py-1 text-xs font-semibold",
            tone === "confirmed"
              ? "border-emerald-200 bg-emerald-50 text-emerald-700"
              : "border-sky-200 bg-sky-50 text-sky-700",
          ].join(" ")}
        >
          {statusLabel(race.status)}
        </span>
      </div>

      <div className="mt-3 flex flex-wrap gap-2 text-xs font-medium text-slate-600">
        <span className="rounded-md bg-slate-100 px-2 py-1">{raceClassLabel(race)}</span>
        <span className="rounded-md bg-slate-100 px-2 py-1">{race.field_size}頭</span>
        <span className="rounded-md bg-slate-100 px-2 py-1">{raceTitle(race).split("・")[0].trim()}</span>
      </div>

      <div className="mt-4 flex-1 border-t border-slate-100 pt-4">
        {forecast && speed ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="m-0 text-xs font-semibold text-slate-500">想定展開</p>
                <p className="m-0 text-lg font-semibold tracking-normal">{speed.beginnerLabel}</p>
              </div>
              <div className="text-right">
                <p className="m-0 text-xs font-semibold text-slate-500">信頼度</p>
                <p className="m-0 text-sm font-semibold text-slate-800">{confidence?.label}</p>
              </div>
            </div>
            {topHorse ? (
              <p className="m-0 rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-700">
                展開が向く候補: <span className="font-semibold text-slate-950">{topHorse}</span>
              </p>
            ) : null}
            {headline ? <p className="m-0 text-sm leading-6 text-slate-600">{headline}</p> : null}
          </div>
        ) : tone === "confirmed" ? (
          <p className="m-0 text-sm leading-6 text-slate-600">
            確定後の流れと各馬の走りを確認できます。
          </p>
        ) : (
          <p className="m-0 text-sm leading-6 text-slate-600">
            出走馬データがそろうと、展開プレビューがここに表示されます。
          </p>
        )}
      </div>

      <span className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-slate-950">
        {raceActionLabel(race)}
        <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" aria-hidden />
      </span>
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

function RaceSection({
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
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {items.map((item) => (
            <RaceCard key={item.race.race_key} item={item} featured={featured} />
          ))}
        </div>
      )}
    </section>
  );
}

export default async function HomePage() {
  const { races, error } = await loadRaces();
  const sortedRaces = [...races].sort(compareRaceSummary);
  const items = error ? [] : await enrichForecasts(sortedRaces);
  const weekend = weekendRange();

  const weekendItems = items.filter(
    ({ race }) => isForecastRace(race) && isRaceInRange(race, weekend),
  );
  const upcomingItems = items.filter(
    ({ race }) =>
      isForecastRace(race) &&
      !weekendItems.some((item) => item.race.race_key === race.race_key),
  );
  const confirmedItems = items.filter(({ race }) => statusTone(race.status) === "confirmed");
  const venueCount = new Set(items.map(({ race }) => race.jyo_cd)).size;

  return (
    <main className="mx-auto max-w-6xl px-5 py-6 text-slate-950">
      <section className="mb-6 rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl">
            <p className="m-0 text-sm font-semibold text-slate-500">Race Board</p>
            <h1 className="m-0 mt-2 text-2xl font-semibold tracking-normal">レース一覧</h1>
            <p className="m-0 mt-2 text-sm leading-6 text-slate-600">
              今週末の予想対象を先頭に、出走前レースと確定後レースを分けて確認できます。
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

      <div className="space-y-9">
        <RaceSection
          id="weekend"
          title="今週末の予想対象"
          description={`${formatRaceDate(weekend.from)} - ${formatRaceDate(weekend.to)} の出走前レース`}
          items={weekendItems}
          featured
        />

        <RaceSection
          id="upcoming"
          title="その他の出走前レース"
          description="展開予想を確認できる未確定レース"
          items={upcomingItems}
        />

        <RaceSection
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
