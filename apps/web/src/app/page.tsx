import Link from "next/link";

// fixtures 由来のサンプルレース。
const UPCOMING_RACE_KEY = "2026062005010101"; // 出走前 → 展開予想
const CONFIRMED_RACE_KEY = "2026061705010101"; // 確定後 → ペース分析

export default function HomePage() {
  return (
    <main className="container home">
      <h1>PCI App — 競馬展開予想</h1>
      <p className="lead">
        PCI を知らなくても、レースの「展開（ペース）」と、その展開で恩恵を受ける馬がわかる。
      </p>

      <div className="cards">
        <Link className="card" href={`/races/${UPCOMING_RACE_KEY}/forecast`}>
          <span className="card-tag">出走前</span>
          <strong>展開予想</strong>
          <span>想定ペース・展開が向く馬（PAI）を見る →</span>
        </Link>
        <Link className="card" href={`/races/${CONFIRMED_RACE_KEY}/pace-analysis`}>
          <span className="card-tag">確定後</span>
          <strong>ペース分析</strong>
          <span>各馬 PCI・実績RPCI・PCI3 を振り返る →</span>
        </Link>
      </div>

      <p className="note">
        ※ 表示には FastAPI バックエンド（<code>API_BASE_URL</code>）の起動が必要です。
      </p>
    </main>
  );
}
