import type { Reason } from "@pci/api-client";

/** 説明可能性の根拠リスト（全判定に付与・設計書 04 §3）。 */
export function ReasonList({ reasons }: { reasons: Reason[] }) {
  if (reasons.length === 0) {
    return null;
  }
  return (
    <ul className="reasons">
      {reasons.map((r, i) => (
        <li key={`${r.code}-${i}`}>
          <span className="reason-desc">{r.description}</span>
          {typeof r.contribution === "number" ? (
            <span className="reason-contrib">
              {r.contribution > 0 ? "+" : ""}
              {r.contribution}
            </span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
