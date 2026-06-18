import Link from "next/link";

export default function ForecastNotFound() {
  return (
    <main className="container">
      <h2>レースが見つかりません</h2>
      <p>指定したレースは未登録か、出走馬がまだ確定していません。</p>
      <Link className="cta" href="/">
        ← トップに戻る
      </Link>
    </main>
  );
}
