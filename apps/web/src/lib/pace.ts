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
  beginnerLabel: string;
  beginnerSummary: string;
  bettingHint: string;
  color: string;
}

const PACE_SPEED_META: Record<PaceSpeedLevel, PaceSpeedMeta> = {
  veryHigh: {
    level: "veryHigh",
    label: "超ハイ",
    symbol: "H++",
    description: "前半負荷がかなり高い流れ。差し・追込の浮上に注意。",
    beginnerLabel: "かなり速い流れ",
    beginnerSummary: "前半からかなり流れそうです。前で運ぶ馬には最後まで粘る力が求められます。",
    bettingHint: "最後に脚を使える馬や、後ろで我慢できる馬を相手に入れておきたいです。",
    color: "#1d4ed8",
  },
  high: {
    level: "high",
    label: "ハイ",
    symbol: "H",
    description: "前半が速めの流れ。持続力と差し脚が活きやすい。",
    beginnerLabel: "やや速い流れ",
    beginnerSummary: "前半から流れそうです。前の馬が苦しくなれば、後ろから運ぶ馬にも出番があります。",
    bettingHint: "長く脚を使える馬や、流れに乗って差せる馬を重視したいです。",
    color: "#2563eb",
  },
  average: {
    level: "average",
    label: "平均",
    symbol: "M",
    description: "標準的な流れ。脚質差は比較的小さめ。",
    beginnerLabel: "平均的な流れ",
    beginnerSummary: "大きく偏らない流れになりそうです。展開だけで極端な有利不利は出にくいです。",
    bettingHint: "展開よりも、近走内容やコース相性を合わせて見たいです。",
    color: "#64748b",
  },
  slow: {
    level: "slow",
    label: "スロー",
    symbol: "S",
    description: "前半が緩めの流れ。逃げ・先行の粘り込みに注意。",
    beginnerLabel: "やや落ち着いた流れ",
    beginnerSummary: "前半は落ち着きそうです。前めで運ぶ馬が余力を残しやすくなります。",
    bettingHint: "前の位置を取れそうな馬や、直線で素早く動ける馬を重視したいです。",
    color: "#dc2626",
  },
  verySlow: {
    level: "verySlow",
    label: "超スロー",
    symbol: "S++",
    description: "前半がかなり緩い流れ。位置取りと瞬発力が重要。",
    beginnerLabel: "かなり落ち着いた流れ",
    beginnerSummary: "前半はかなり落ち着きそうです。後ろから届かせるには一気に動ける力が必要です。",
    bettingHint: "前めで運べる馬と、短い直線勝負に強い馬を中心に見たいです。",
    color: "#991b1b",
  },
  unknown: {
    level: "unknown",
    label: "判定不可",
    symbol: "-",
    description: "判定に必要な指標がありません。",
    beginnerLabel: "判断材料が不足",
    beginnerSummary: "流れをはっきり決めるだけの材料が足りません。",
    bettingHint: "展開は決めつけず、馬の地力や近走内容も広めに見てください。",
    color: "#94a3b8",
  },
};

const RAW_INDEX_WITH_VALUE = /\b(?:PCI3?|RPCI|PAI)\b\s*(?:は|が|:|：|=|＝)?\s*\d+(?:\.\d+)?/gi;
const RAW_INDEX_NAME = /\b(?:PCI3?|RPCI|PAI)\b/gi;
const DECIMAL_VALUE = /\d+\.\d+/g;

/**
 * 初心者向けコメントの最終防衛線。
 * API や AI 生成文に専門指標・小数が混ざっても、表示直前に読み物として丸める。
 */
export function sanitizeBeginnerComment(text: string): string {
  return text
    .replace(RAW_INDEX_WITH_VALUE, "ペース判定")
    .replace(RAW_INDEX_NAME, "ペース指標")
    .replace(DECIMAL_VALUE, "具体的な数値");
}

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

export type BenefitRoleTone = "main" | "partner" | "value" | "keep";

export interface BenefitRecommendation {
  label: string;
  tone: BenefitRoleTone;
  reason: string;
}

function styleBenefitReason(style: string): string {
  if (style.includes("逃")) {
    return "前で自分の形を作れれば、流れの後押しを受けやすいタイプです。";
  }
  if (style.includes("先")) {
    return "好位で流れに乗れるため、極端なロスなく力を出しやすいタイプです。";
  }
  if (style.includes("差")) {
    return "前が苦しくなる流れなら、直線で脚を伸ばしやすいタイプです。";
  }
  if (style.includes("追")) {
    return "展開が速くなれば、後半に浮上する余地があるタイプです。";
  }
  return "今回の流れとかみ合えば、力を出しやすいタイプです。";
}

/** 展開恩恵馬を、馬券検討で使いやすい役割ラベルへ変換する。 */
export function benefitRecommendation(horse: Pick<HorseFit, "pai" | "running_style">, rank: number): BenefitRecommendation {
  const reason = styleBenefitReason(horse.running_style);

  if (rank === 0 && horse.pai >= 80) {
    return {
      label: "軸候補",
      tone: "main",
      reason: `${reason} まず中心として確認したい一頭です。`,
    };
  }

  if (rank <= 2 && horse.pai >= 70) {
    return {
      label: "相手候補",
      tone: "partner",
      reason: `${reason} 上位候補の相手として押さえたい一頭です。`,
    };
  }

  if (horse.pai >= 70) {
    return {
      label: "穴で拾う",
      tone: "value",
      reason: `${reason} 人気次第では妙味を見込めます。`,
    };
  }

  return {
    label: "押さえ",
    tone: "keep",
    reason: `${reason} 強く決め打たず、相手までで考えたい一頭です。`,
  };
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
