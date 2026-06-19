import Link from "next/link";
import { notFound } from "next/navigation";

import { CommentCard } from "@/components/CommentCard";
import { PaceAnalysisTable } from "@/components/PaceAnalysisTable";
import { ReasonList } from "@/components/ReasonList";
import { api } from "@/lib/api";
import { ApiError, type PaceAnalysis } from "@pci/api-client";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ raceKey: string }>;
}

function fmt(value: number | null | undefined): string {
  return value !== null && value !== undefined ? value.toFixed(1) : "—";
}

export default async function PaceAnalysisPage({ params }: PageProps) {
  const { raceKey } = await params;

  let analysis: PaceAnalysis;
  try {
    analysis = await api.getPaceAnalysis(raceKey);
  } catch (err) {
    if (err instanceof ApiError && (err.status === 404 || err.status === 409)) {
      notFound();
    }
    throw err;
  }

  const horses = analysis.horses ?? [];

  return (
    <main className="container">
      <p className="breadcrumb">
        <Link href="/">← トップ</Link>
        <span className="race-key">{analysis.race_key}</span>
      </p>

      <section className="headline" style={{ borderColor: "#0f172a" }}>
        <span className="headline-tag" style={{ background: "#0f172a" }}>
          確定後ペース分析
        </span>
        <h2 className="headline-title">レースの実際のペースを PCI で振り返る</h2>
        <dl className="metrics">
          <div>
            <dt>実績RPCI</dt>
            <dd>{fmt(analysis.rpci_actual)}</dd>
          </div>
          <div>
            <dt>PCI3</dt>
            <dd>{fmt(analysis.pci3_actual)}</dd>
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
        <h3>各馬 PCI（着順・★=PCI3 寄与）</h3>
        <PaceAnalysisTable horses={horses} />
      </section>
    </main>
  );
}
