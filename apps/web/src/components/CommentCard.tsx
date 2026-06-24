import { ReasonList } from "@/components/ReasonList";
import { sanitizeBeginnerComment } from "@/lib/pace";
import type { Comment } from "@pci/api-client";

/**
 * 展開コメント（自然文の解説）。
 *
 * 専門指標を「読み物」に翻訳し、PCI を知らないファンが最初に目を通す導入として
 * 機能する（コアバリュー）。生成方式（model_version）は根拠内に閉じ、本文からは遠ざける。
 */
export function CommentCard({ comment }: { comment: Comment }) {
  const headline = sanitizeBeginnerComment(comment.headline);
  const body = (comment.body ?? []).map(sanitizeBeginnerComment);
  const reasons = comment.reasons ?? [];

  return (
    <section className="panel comment-card">
      <h3>この展開をやさしく解説</h3>
      <p className="comment-lead">{headline}</p>
      {body.map((para, i) => (
        <p key={i} className="comment-para">
          {para}
        </p>
      ))}
      <details className="rationale">
        <summary>コメントの根拠</summary>
        <p className="comment-model">生成方式: {comment.model_version}</p>
        <ReasonList reasons={reasons} />
      </details>
    </section>
  );
}
