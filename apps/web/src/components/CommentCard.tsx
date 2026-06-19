import { ReasonList } from "@/components/ReasonList";
import type { Comment } from "@pci/api-client";

/**
 * 展開コメント（自然文の解説）。
 *
 * RPCI・PAI といった指標を「読み物」に翻訳し、PCI を知らないファンが
 * 最初に目を通す導入として機能する（コアバリュー）。生成方式（model_version）は
 * 根拠として明示し、説明可能性を担保する。
 */
export function CommentCard({ comment }: { comment: Comment }) {
  const body = comment.body ?? [];
  const reasons = comment.reasons ?? [];

  return (
    <section className="panel comment-card">
      <h3>この展開をやさしく解説</h3>
      <p className="comment-lead">{comment.headline}</p>
      {body.map((para, i) => (
        <p key={i} className="comment-para">
          {para}
        </p>
      ))}
      <details className="rationale">
        <summary>コメントの根拠（{comment.model_version}）</summary>
        <ReasonList reasons={reasons} />
      </details>
    </section>
  );
}
