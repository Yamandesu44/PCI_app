/**
 * 展開表示のための純粋プレゼンテーションロジック。
 *
 * 本プロダクトのコアバリュー「PCI を理解していない競馬ファンでも展開予想を活用できる」を
 * 体現する層。専門用語（RPCI・PAI）を非専門家向けの言葉・色・並びへ変換する。
 * 副作用なし・決定的なので vitest で単体テストする。
 */
import type { ForecastAccuracy, HorseFit, StyleAdvantage } from "@pci/api-client";

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

/** 内部指数を使わず、3分類の展開ラベルを初心者向けの表現へ変換する。 */
export function beginnerPaceLabel(label: string): string {
  if (label === "ハイ") return "速い流れ";
  if (label === "スロー") return "落ち着いた流れ";
  if (label === "平均") return "平均的な流れ";
  return "判断材料が不足";
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

export type ConfidenceTone = "strong" | "normal" | "caution";

export interface ConfidenceInsight {
  pct: number;
  label: string;
  tone: ConfidenceTone;
  summary: string;
  bettingHint: string;
}

/** 展開信頼度を、初心者にも判断しやすい自然語へ変換する。 */
export function confidenceInsight(confidence: number): ConfidenceInsight {
  const pct = Math.max(0, Math.min(100, Math.round(confidence * 100)));

  if (pct >= 70) {
    return {
      pct,
      label: "読みやすい",
      tone: "strong",
      summary: "展開の方向性が比較的はっきりしています。",
      bettingHint: "中心候補を決めて、相手を絞る検討がしやすいレースです。",
    };
  }

  if (pct >= 50) {
    return {
      pct,
      label: "標準",
      tone: "normal",
      summary: "大きく崩れにくい一方で、決めつけすぎは避けたい信頼度です。",
      bettingHint: "展開が向く馬を重視しつつ、地力上位も残して見たいレースです。",
    };
  }

  return {
    pct,
    label: "変動注意",
    tone: "caution",
    summary: "展開が読み切りにくく、想定と違う流れになる余地があります。",
    bettingHint: "軸を強く決めすぎず、相手候補を少し広めに見たいレースです。",
  };
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

/**
 * 馬番の表示ラベルを作る。
 *
 * frame_no=0 は特別登録段階で枠順未確定を意味し、horse_no は ingest 側が
 * 割り当てた暫定の仮番号である可能性がある（確定済みの公式馬番ではない）。
 * 未確定時にそのまま「馬番」と表示すると確定情報であるかのように誤解されるため、
 * 枠順確定後（frame_no 1〜8）と区別してラベル化する。
 */
export function horseNumberLabel(horse: Pick<HorseFit, "horse_no" | "frame_no">): string {
  if (horse.frame_no > 0) {
    return `馬番 ${horse.horse_no}`;
  }
  return `登録順 ${horse.horse_no}（馬番未確定）`;
}

export type RaceSpotlightTone = "focus" | "value" | "caution" | "normal";

export interface RaceSpotlight {
  label: string;
  tone: RaceSpotlightTone;
  reason: string;
}

/** 一覧画面で、先に確認したいレースかどうかを短いラベルにする。 */
export function raceSpotlight({
  confidence,
  fieldSize,
  horses,
  topPai: suppliedTopPai,
  topFitStrength,
}: {
  confidence: number;
  fieldSize: number;
  horses?: HorseFit[];
  topPai?: number;
  topFitStrength?: "strong" | "notable" | "normal" | string;
}): RaceSpotlight {
  const topHorse = sortByPai(horses ?? [])[0];
  const topPai = suppliedTopPai
    ?? (topFitStrength === "strong" ? 80 : topFitStrength === "notable" ? 70 : undefined)
    ?? topHorse?.pai
    ?? 0;

  if (confidence >= 0.7 && topPai >= 80) {
    return {
      label: "注目",
      tone: "focus",
      reason: "展開の読み筋と中心候補がそろっています。",
    };
  }

  if (confidence < 0.5) {
    return {
      label: "波乱注意",
      tone: "caution",
      reason: "展開が読み切りにくく、決め打ちは控えたいレースです。",
    };
  }

  if (fieldSize >= 14 && topPai >= 70) {
    return {
      label: "妙味",
      tone: "value",
      reason: "頭数が多く、展開で浮上する候補を探しやすいレースです。",
    };
  }

  return {
    label: "通常",
    tone: "normal",
    reason: "基本情報を確認してから詳細を見るレースです。",
  };
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

export type DiscountTone = "avoid" | "caution";

export interface DiscountRecommendation {
  label: string;
  tone: DiscountTone;
  reason: string;
}

function styleDiscountReason(style: string): string {
  if (style.includes("逃")) {
    return "前に行く形が取れないと、持ち味を出しにくくなります。";
  }
  if (style.includes("先")) {
    return "好位で運べない流れになると、最後まで踏ん張りにくくなります。";
  }
  if (style.includes("差")) {
    return "前が止まりにくい流れでは、直線で届き切らないリスクがあります。";
  }
  if (style.includes("追")) {
    return "展開の助けが少ないと、後ろから届かせるには条件が厳しくなります。";
  }
  return "今回の流れとかみ合わない場合、力を出し切れない可能性があります。";
}

/** 展開面から評価を下げたい馬を、検討用の自然語に変換する。 */
export function discountRecommendation(
  horse: Pick<HorseFit, "fit_label" | "pai" | "running_style">,
): DiscountRecommendation {
  const reason = styleDiscountReason(horse.running_style);

  if (horse.fit_label === "不利" || horse.pai < 45) {
    return {
      label: "評価下げ",
      tone: "avoid",
      reason: `${reason} 人気しているなら慎重に扱いたい一頭です。`,
    };
  }

  return {
    label: "過信注意",
    tone: "caution",
    reason: `${reason} 強く買い切るより、相手までで考えたい一頭です。`,
  };
}

/** 展開が向きにくい馬を、割引度が高い順に返す。 */
export function sortDiscountCandidates(horses: HorseFit[]): HorseFit[] {
  return [...horses].sort((a, b) => {
    const aPenalty = a.fit_label === "不利" ? 0 : 1;
    const bPenalty = b.fit_label === "不利" ? 0 : 1;
    return aPenalty - bPenalty || a.pai - b.pai;
  });
}

export interface ForecastDecisionChecklistItem {
  label: string;
  value: string;
  detail: string;
}

function horseName(horse: HorseFit): string {
  return horse.horse_name ?? horseNumberLabel(horse);
}

/** 詳細画面の冒頭で見せる「今回どう見るか」の要約を作る。 */
export function forecastDecisionChecklist({
  predictedRpci,
  confidence,
  horses,
}: {
  predictedRpci: number | null | undefined;
  confidence: number;
  horses: HorseFit[];
}): ForecastDecisionChecklistItem[] {
  const speed = paceSpeedFromIndex(predictedRpci);
  const confidenceMeta = confidenceInsight(confidence);
  const topHorse = sortByPai(horses)[0];
  const topRecommendation = topHorse ? benefitRecommendation(topHorse, 0) : null;

  return [
    {
      label: "展開",
      value: speed.beginnerLabel,
      detail: speed.bettingHint,
    },
    {
      label: "中心候補",
      value: topHorse ? `${horseName(topHorse)} / ${topRecommendation?.label}` : "判断材料が不足",
      detail:
        topHorse && topRecommendation
          ? topRecommendation.reason
          : "出走馬データがそろうと、展開が向きそうな馬を表示します。",
    },
    {
      label: "検討方針",
      value: confidenceMeta.label,
      detail: confidenceMeta.bettingHint,
    },
  ];
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

export interface StyleAdvantageScore {
  key: string;
  label: string;
  /** 50=互角。大きいほど今回の想定ペースが向く。 */
  value: number;
  description: string;
  /** 有利/互角/不利の言葉ラベル（数字が苦手なユーザー向け）。 */
  verdict: string;
}

const STYLE_DESCRIPTIONS: Record<string, string> = {
  逃げ: "前半から主導権を取る馬",
  先行: "好位で流れに乗る馬",
  差し: "中団から末脚を伸ばす馬",
  追込: "後方待機で直線勝負の馬",
};

function styleVerdict(score: number): string {
  if (score >= 65) return "有利";
  if (score >= 55) return "やや有利";
  if (score > 45) return "互角";
  if (score > 35) return "やや不利";
  return "不利";
}

/**
 * API の脚質別有利度（style-advantage-v1、50=互角）を表示用に変換する。
 * 以前は web 側でその脚質の最大PAIを流用しており、スコアが高止まりして
 * 差が出なかった。算出はドメイン層（想定RPCIの中立点からの乖離）へ移した。
 */
export function styleAdvantageScores(advantage: StyleAdvantage): StyleAdvantageScore[] {
  return advantage.entries.map((entry) => ({
    key: entry.style,
    label: entry.style,
    value: Math.round(entry.score),
    description: STYLE_DESCRIPTIONS[entry.style] ?? "",
    verdict: styleVerdict(entry.score),
  }));
}

export type ForecastAccuracyTone = "hit" | "miss";

export interface ForecastAccuracyMeta {
  tone: ForecastAccuracyTone;
  label: string;
  summary: string;
  color: string;
}

/**
 * 出走前の想定と実績の答え合わせを、非専門家向けの言葉・色に変換する。
 * predicted_rpci/actual_rpci/error（実数値）は表示に使わない
 * （PROJECT_RULES §5: UI に PCI/RPCI 実数値を出さない）。
 */
export function forecastAccuracyMeta(
  accuracy: Pick<ForecastAccuracy, "label_hit" | "predicted_label" | "actual_label">,
): ForecastAccuracyMeta {
  if (accuracy.label_hit) {
    return {
      tone: "hit",
      label: "想定的中",
      summary: `事前の想定「${accuracy.predicted_label}」が実際の流れと一致しました。`,
      color: "#16a34a",
    };
  }
  return {
    tone: "miss",
    label: "想定と相違",
    summary: `事前の想定は「${accuracy.predicted_label}」でしたが、実際は「${accuracy.actual_label}」という流れでした。`,
    color: "#d97706",
  };
}
