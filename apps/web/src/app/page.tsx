import Link from "next/link";

// fixtures 由来のサンプルレース（ingestion-worker/fixtures と整合）。
const SAMPLE_RACE_KEY = "2026062005010101";

export default function HomePage() {
  return (
    <main className="container home">
      <h1>PCI App — 競馬展開予想</h1>
      <p className="lead">
        PCI を知らなくても、レースの「展開（ペース）」と、その展開で恩恵を受ける馬がわかる。
      </p>
      <Link className="cta" href={`/races/${SAMPLE_RACE_KEY}/forecast`}>
        サンプルレースの展開予想を見る →
      </Link>
      <p className="note">
        ※ 表示には FastAPI バックエンド（<code>API_BASE_URL</code>）の起動が必要です。
      </p>
    </main>
  );
}
