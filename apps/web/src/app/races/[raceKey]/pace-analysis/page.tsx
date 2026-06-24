import Link from "next/link";
import { notFound } from "next/navigation";

import { CommentCard } from "@/components/CommentCard";
import { PaceAnalysisTable } from "@/components/PaceAnalysisTable";
import { RaceHero } from "@/components/RaceHero";
import { ReasonList } from "@/components/ReasonList";
import { api } from "@/lib/api";
import { paceSpeedFromIndex } from "@/lib/pace";
import { ApiError, type PaceAnalysis, type RaceDetail } from "@pci/api-client";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ raceKey: string }>;
}

export default async function PaceAnalysisPage({ params }: PageProps) {
  const { raceKey } = await params;

  let analysis: PaceAnalysis;
  let race: RaceDetail;
  try {
    [analysis, race] = await Promise.all([
      api.getPaceAnalysis(raceKey),
      api.getRaceDetail(raceKey),
    ]);
  } catch (err) {
    if (err instanceof ApiError && (err.status === 404 || err.status === 409)) {
      notFound();
    }
    throw err;
  }

  const horses = analysis.horses ?? [];
  const resultSpeed = paceSpeedFromIndex(analysis.rpci_actual);
  const pci3Speed = paceSpeedFromIndex(analysis.pci3_actual);

  return (
    <main className="container">
      <p className="breadcrumb">
        <Link href="/">← トップ</Link>
        <span className="race-key">{analysis.race_key}</span>
      </p>

      <RaceHero race={race} mode="analysis" />

      <section className="headline" style={{ borderColor: "#0f172a" }}>
        <span className="headline-tag" style={{ background: "#0f172a" }}>
          確定後ペース分析
        </span>
        <h2 className="headline-title">レースの実際のペースを PCI で振り返る</h2>
        <dl className="metrics">
          <div>
            <dt>実績ペース</dt>
            <dd style={{ color: resultSpeed.color }}>
              {resultSpeed.symbol} {resultSpeed.label}
            </dd>
          </div>
          <div>
            <dt>上位3頭ペース</dt>
            <dd style={{ color: pci3Speed.color }}>
              {pci3Speed.symbol} {pci3Speed.label}
            </dd>
          </div>
          <div>
            <dt>対象頭数</dt>
            <dd>{analysis.sample_size}</dd>
          </div>
          <div>
            <dt>式</dt>
            <dd>
              <code>{analysis.formula_version}</code>
            </dd>
          </div>
        </dl>
        <details className="rationale">
          <summary>算出の根拠</summary>
          <ReasonList reasons={analysis.reasons ?? []} />
        </details>
      </section>

      {analysis.comment ? <CommentCard comment={analysis.comment} /> : null}

      <section className="panel">
        <h3>各馬 PCI判定（着順・★=上位3頭ペース寄与）</h3>
        <PaceAnalysisTable horses={horses} />
      </section>
    </main>
  );
}
