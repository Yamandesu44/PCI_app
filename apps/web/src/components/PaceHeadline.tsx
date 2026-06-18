import { ReasonList } from "@/components/ReasonList";
import { paceMeta } from "@/lib/pace";
import type { Reason } from "@pci/api-client";

interface PaceHeadlineProps {
  headline: string;
  detail: string;
  paceLabel: string;
  predictedRpci: number;
  confidence: number;
  modelVersion: string;
  reasons: Reason[];
}

/** 展開予想の見出し。専門用語に頼らず「どんな流れか」を最初に伝える。 */
export function PaceHeadline({
  headline,
  detail,
  paceLabel,
  predictedRpci,
  confidence,
  modelVersion,
  reasons,
}: PaceHeadlineProps) {
  const meta = paceMeta(paceLabel);
  const confidencePct = Math.round(confidence * 100);

  return (
    <section className="headline" style={{ borderColor: meta.color }}>
      <span className="headline-tag" style={{ background: meta.color }}>
        {paceLabel}ペース
      </span>
      <h2 className="headline-title">{headline}</h2>
      <p className="headline-summary">{meta.summary}</p>
      <p className="headline-detail">{detail}</p>

      <dl className="metrics">
        <div>
          <dt>想定RPCI</dt>
          <dd>{predictedRpci.toFixed(1)}</dd>
        </div>
        <div>
          <dt>確信度</dt>
          <dd>{confidencePct}%</dd>
        </div>
        <div>
          <dt>モデル</dt>
          <dd>
            <code>{modelVersion}</code>
          </dd>
        </div>
      </dl>

      <details className="rationale">
        <summary>予測の根拠</summary>
        <ReasonList reasons={reasons} />
      </details>
    </section>
  );
}
