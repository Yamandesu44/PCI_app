import { ReasonList } from "@/components/ReasonList";
import { sanitizeBeginnerComment } from "@/lib/pace";
import type { Comment } from "@pci/api-client";
import { Sparkles } from "lucide-react";

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
    <section className="rounded-lg border border-emerald-200 bg-emerald-50/70 p-5 shadow-sm">
      <div className="flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-emerald-700" aria-hidden />
        <h2 className="m-0 text-base font-semibold text-slate-950">このレースをやさしく解説</h2>
      </div>
      <p className="m-0 mt-3 text-sm font-semibold leading-6 text-slate-950">{headline}</p>
      {body.map((para, i) => (
        <p key={i} className="m-0 mt-2 text-sm leading-6 text-slate-700">
          {para}
        </p>
      ))}
      <details className="mt-4">
        <summary className="cursor-pointer text-xs font-semibold text-emerald-700">
          コメントの根拠
        </summary>
        <p className="mb-0 mt-2 text-xs text-slate-500">生成方式: {comment.model_version}</p>
        <ReasonList reasons={reasons} />
      </details>
    </section>
  );
}
