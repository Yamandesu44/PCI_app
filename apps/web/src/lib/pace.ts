/**
 * 展開表示のための純粋プレゼンテーションロジック。
 *
 * 本プロダクトのコアバリュー「PCI を理解していない競馬ファンでも展開予想を活用できる」を
 * 体現する層。専門用語（RPCI・PAI）を非専門家向けの言葉・色・並びへ変換する。
 * 副作用なし・決定的なので vitest で単体テストする。
 */
import type { HorseFit } from "@pci/api-client";

export type PaceTone = "high" | "average" | "slow";

export interface PaceMeta {
  tone: PaceTone;
  /** 非専門家向けの一言サマリ。 */
  summary: string;
  /** UI 強調色（HEX）。 */
  color: string;
}

const PACE_META: Record<string, PaceMeta> = {
  ハイ: {
    tone: "high",
    summary: "前半から速い流れ。差し・追い込みが届きやすい展開です。",
    color: "#2563eb",
  },
  平均: {
    tone: "average",
    summary: "平均的な流れ。脚質による有利・不利は小さめです。",
    color: "#64748b",
  },
  スロー: {
    tone: "slow",
    summary: "前半が緩い流れ。逃げ・先行が粘りやすい展開です。",
    color: "#dc2626",
  },
};

const FALLBACK_PACE: PaceMeta = {
  tone: "average",
  summary: "展開傾向は中立とみています。",
  color: "#64748b",
};

export function paceMeta(label: string): PaceMeta {
  return PACE_META[label] ?? FALLBACK_PACE;
}

export type PaceSpeedLevel =
  | "veryHigh"
  | "high"
  | "average"
  | "slow"
  | "verySlow"
  | "unknown";

export interface PaceSpeedMeta {
  level: PaceSpeedLevel;
  label: string;
  symbol: string;
  description: string;
  color: string;
}

const PACE_SPEED_META: Record<PaceSpeedLevel, PaceSpeedMeta> = {
  veryHigh: {
    level: "veryHigh",
    label: "超ハイ",
    symbol: "H++",
    description: "前半負荷がかなり高い流れ。差し・追込の浮上に注意。",
    color: "#1d4ed8",
  },
  high: {
    level: "high",
    label: "ハイ",
    symbol: "H",
    description: "前半が速めの流れ。持続力と差し脚が活きやすい。",
    color: "#2563eb",
  },
  average: {
    level: "average",
    label: "平均",
    symbol: "M",
    description: "標準的な流れ。脚質差は比較的小さめ。",
    color: "#64748b",
  },
  slow: {
    level: "slow",
    label: "スロー",
    symbol: "S",
    description: "前半が緩めの流れ。逃げ・先行の粘り込みに注意。",
    color: "#dc2626",
  },
  verySlow: {
    level: "verySlow",
    label: "超スロー",
    symbol: "S++",
    description: "前半がかなり緩い流れ。位置取りと瞬発力が重要。",
    color: "#991b1b",
  },
  unknown: {
    level: "unknown",
    label: "判定不可",
    symbol: "-",
    description: "判定に必要な指標がありません。",
    color: "#94a3b8",
  },
};

/** PCI/RPCI/PCI3の実数値を、非専門家向けの5段階ペース速度へ変換する。 */
export function paceSpeedFromIndex(value: number | null | undefined): PaceSpeedMeta {
  if (value === null || value === undefined) return PACE_SPEED_META.unknown;
  if (value < 47) return PACE_SPEED_META.veryHigh;
  if (value < 50) return PACE_SPEED_META.high;
  if (value <= 52) return PACE_SPEED_META.average;
  if (value <= 55) return PACE_SPEED_META.slow;
  return PACE_SPEED_META.verySlow;
}

export function paceSpeedLabel(value: number | null | undefined): string {
  return paceSpeedFromIndex(value).label;
}

export function paceSpeedSymbol(value: number | null | undefined): string {
  return paceSpeedFromIndex(value).symbol;
}

export type FitTone = "matched" | "neutral" | "unfavorable";

export function fitTone(label: string): FitTone {
  if (label === "合致") return "matched";
  if (label === "不利") return "unfavorable";
  return "neutral";
}

/** PAI(0–100) を表示バー幅(%) に変換。範囲外は丸める。 */
export function paiBarWidth(pai: number): number {
  return Math.max(0, Math.min(100, Math.round(pai)));
}

/** 合致馬を PAI 降順で返す（入力配列は変更しない）。 */
export function sortByPai(horses: HorseFit[]): HorseFit[] {
  return [...horses].sort((a, b) => b.pai - a.pai);
}

export type PciTone = "slow" | "high" | "even" | "unknown";

/**
 * 個馬 PCI を傾向に分類（CLAUDE.md の定義）。
 *   PCI > 50: スロー（後半型） / PCI < 50: ハイ（前傾） / = 50: イーブン
 */
export function pciTone(pci: number | null | undefined): PciTone {
  if (pci === null || pci === undefined) return "unknown";
  if (pci > 50) return "slow";
  if (pci < 50) return "high";
  return "even";
}

const PCI_TONE_LABEL: Record<PciTone, string> = {
  slow: "スロー",
  high: "ハイ",
  even: "イーブン",
  unknown: "—",
};

const PCI_TONE_COLOR: Record<PciTone, string> = {
  slow: "#dc2626",
  high: "#2563eb",
  even: "#64748b",
  unknown: "#94a3b8",
};

export function pciToneLabel(tone: PciTone): string {
  return PCI_TONE_LABEL[tone];
}

export function pciToneColor(tone: PciTone): string {
  return PCI_TONE_COLOR[tone];
}
