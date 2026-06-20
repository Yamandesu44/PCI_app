import Link from "next/link";

import { api } from "@/lib/api";
import { formatRaceDate, raceHref, raceTitle, statusLabel, statusTone } from "@/lib/races";
import { ApiError, type RaceSummary } from "@pci/api-client";

// レース一覧は実行時にバックエンドへ問い合わせる（ビルド時フェッチを避ける）。
export const dynamic = "force-dynamic";

async function loadRaces(): Promise<{ races: RaceSummary[]; error: string | null }> {
  try {
    return { races: await api.listRaces(), error: null };
  } catch (err) {
    const detail =
      err instanceof ApiError ? `APIエラー (${err.status})` : "APIに接続できませんでした";
    return { races: [], error: detail };
  }
}

export default async function HomePage() {
  const { races, error } = await loadRaces();

  return (
    <main className="container home">
      <h1>PCI App — 競馬展開予想</h1>
      <p className="lead">
        PCI を知らなくても、レースの「展開（ペース）」と、その展開で恩恵を受ける馬がわかる。
      </p>

      <section className="panel">
        <h3>レースを選ぶ</h3>

        {error ? (
          <p className="empty">
            レース一覧を取得できませんでした（{error}）。
            <br />
            FastAPI バックエンド（<code>API_BASE_URL</code>）が起動しているか確認してください。
          </p>
        ) : races.length === 0 ? (
          <p className="empty">
            表示できるレースがありません。ingestion-worker でデータを取り込んでください。
          </p>
        ) : (
          <ul className="race-list">
            {races.map((race) => (
              <li key={race.race_key}>
                <Link className="card race-card" href={raceHref(race)}>
                  <span className={`card-tag ${statusTone(race.status)}`}>
                    {statusLabel(race.status)}
                  </span>
                  <strong>{raceTitle(race)}</strong>
                  <span>
                    {formatRaceDate(race.race_date)} ・ {race.field_size}頭立て ・{" "}
                    {statusTone(race.status) === "confirmed"
                      ? "ペース分析を見る →"
                      : "展開予想を見る →"}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <p className="note">
        ※ 表示には FastAPI バックエンド（<code>API_BASE_URL</code>）の起動が必要です。
      </p>
    </main>
  );
}
