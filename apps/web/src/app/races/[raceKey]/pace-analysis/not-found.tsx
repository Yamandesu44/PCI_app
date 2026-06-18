import Link from "next/link";

export default function PaceAnalysisNotFound() {
  return (
    <main className="container">
      <h2>ペース分析を表示できません</h2>
      <p>レースが未登録か、まだ結果が確定していません（確定後に PCI を集計します）。</p>
      <Link className="cta" href="/">
        ← トップに戻る
      </Link>
    </main>
  );
}
