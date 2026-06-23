import Link from "next/link";

import { api } from "@/lib/api";
import { isForecastRace, isRaceInRange, weekendRange } from "@/lib/raceSchedule";
import { formatRaceDate, raceHref, raceTitle, statusLabel, statusTone } from "@/lib/races";
import { ApiError, type RaceSummary } from "@pci/api-client";

// レース一覧は実行時にバックエンドへ問い合わせる（ビルド時フェッチを避ける）。
export const dynamic = "force-dynamic";

async function loadRaces(): Promise<{ races: RaceSummary[]; error: string | null }> {
  try {
    return { races: await api.listRaces(100), error: null };
  } catch (err) {
    const detail =
      err instanceof ApiError ? `APIエラー (${err.status})` : "APIに接続できませんでした";
    return { races: [], error: detail };
  }
}

function RaceCard({ race }: { race: RaceSummary }) {
  const tone = statusTone(race.status);
  return (
    <Link className="card race-card" href={raceHref(race)}>
      <span className={`card-tag ${tone}`}>{statusLabel(race.status)}</span>
      <strong>{raceTitle(race)}</strong>
      <span>
        {formatRaceDate(race.race_date)} ・ {race.field_size}頭立て ・{" "}
        {tone === "confirmed" ? "ペース分析を見る →" : "展開予想を見る →"}
      </span>
    </Link>
  );
}

export default async function HomePage() {
  const { races, error } = await loadRaces();
  const weekend = weekendRange();
  const weekendForecasts = races.filter(
    (race) => isForecastRace(race) && isRaceInRange(race, weekend),
  );
  const otherRaces = races.filter(
    (race) => !weekendForecasts.some((target) => target.race_key === race.race_key),
  );

  return (
    <main className="container home">
      <h1>PCI App — 競馬展開予想 SaaS</h1>
      <p className="lead">
        出走前レースは展開予想、確定後レースはペース分析へ。今週末の予想対象を先に確認できます。
      </p>

      <section className="panel">
        <h3>今週末の予想対象</h3>
        <p className="note" style={{ marginTop: 0 }}>
          対象期間: {formatRaceDate(weekend.from)} - {formatRaceDate(weekend.to)}
        </p>

        {error ? (
          <p className="empty">
            レース一覧を取得できませんでした（{error}）。
            <br />
            FastAPI バックエンド（<code>API_BASE_URL</code>）が起動しているか確認してください。
          </p>
        ) : weekendForecasts.length === 0 ? (
          <p className="empty">
            今週末の出走前レースがまだ登録されていません。
            <br />
            JV-Link取り込み、または開発用seedで出走前レースを登録すると、ここに展開予想が表示されます。
          </p>
        ) : (
          <ul className="race-list">
            {weekendForecasts.map((race) => (
              <li key={race.race_key}>
                <RaceCard race={race} />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel">
        <h3>その他のレース</h3>

        {error ? null : otherRaces.length === 0 ? (
          <p className="empty">表示できるレースがありません。</p>
        ) : (
          <ul className="race-list">
            {otherRaces.map((race) => (
              <li key={race.race_key}>
                <RaceCard race={race} />
              </li>
            ))}
          </ul>
        )}
      </section>

      <p className="note">
        ※ 今週末の予想には、出走前レース（status=entries）と出走馬データの登録が必要です。
      </p>
    </main>
  );
}
