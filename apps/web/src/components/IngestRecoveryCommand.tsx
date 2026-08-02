"use client";

import { Check, CircleAlert, Copy } from "lucide-react";
import { useState } from "react";

type CopyState = "idle" | "copied" | "failed";

export function IngestRecoveryCommand({ command }: { command: string }) {
  const [copyState, setCopyState] = useState<CopyState>("idle");

  async function copyCommand() {
    try {
      await navigator.clipboard.writeText(command);
      setCopyState("copied");
      window.setTimeout(() => setCopyState("idle"), 2000);
    } catch {
      setCopyState("failed");
    }
  }

  const Icon = copyState === "copied" ? Check : copyState === "failed" ? CircleAlert : Copy;
  const label =
    copyState === "copied"
      ? "コピーしました"
      : copyState === "failed"
        ? "コピーできませんでした"
        : "再同期コマンドをコピー";

  return (
    <div className="mt-2 flex min-w-0 items-stretch overflow-hidden rounded border border-slate-300 bg-white">
      <code className="min-w-0 flex-1 overflow-x-auto whitespace-nowrap px-3 py-2 font-mono text-[11px] leading-5 text-slate-700">
        {command}
      </code>
      <button
        type="button"
        onClick={copyCommand}
        className="flex h-11 w-11 shrink-0 items-center justify-center border-l border-slate-200 text-slate-500 hover:bg-slate-50 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
        aria-label={label}
        title={label}
      >
        <Icon className="h-4 w-4" aria-hidden />
      </button>
    </div>
  );
}
