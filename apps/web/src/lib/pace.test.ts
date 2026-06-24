import { describe, expect, it } from "vitest";

import {
  benefitRecommendation,
  confidenceInsight,
  fitTone,
  paceMeta,
  paceSpeedFromIndex,
  paiBarWidth,
  pciTone,
  pciToneLabel,
  sanitizeBeginnerComment,
  sortByPai,
} from "./pace";

describe("paceMeta", () => {
  it("既知ラベルを tone に対応づける", () => {
    expect(paceMeta("ハイ").tone).toBe("high");
    expect(paceMeta("平均").tone).toBe("average");
    expect(paceMeta("スロー").tone).toBe("slow");
  });

  it("未知ラベルは中立にフォールバックする", () => {
    expect(paceMeta("???").tone).toBe("average");
    expect(paceMeta("???").summary).toContain("中立");
  });
});

describe("fitTone", () => {
  it("合致ラベルを tone に対応づける", () => {
    expect(fitTone("合致")).toBe("matched");
    expect(fitTone("不利")).toBe("unfavorable");
    expect(fitTone("中立")).toBe("neutral");
  });
});

describe("paceSpeedFromIndex", () => {
  it("PCI/RPCI系の数値を5段階のペース速度に分類する", () => {
    expect(paceSpeedFromIndex(46.9).label).toBe("超ハイ");
    expect(paceSpeedFromIndex(47).label).toBe("ハイ");
    expect(paceSpeedFromIndex(50).label).toBe("平均");
    expect(paceSpeedFromIndex(52).label).toBe("平均");
    expect(paceSpeedFromIndex(52.1).label).toBe("スロー");
    expect(paceSpeedFromIndex(55.1).label).toBe("超スロー");
  });

  it("null/undefinedは判定不可にする", () => {
    expect(paceSpeedFromIndex(null).label).toBe("判定不可");
    expect(paceSpeedFromIndex(undefined).symbol).toBe("-");
  });

  it("初心者向けラベルを持つ", () => {
    expect(paceSpeedFromIndex(48).beginnerLabel).toBe("やや速い流れ");
    expect(paceSpeedFromIndex(53).beginnerSummary).toContain("前半");
  });
});

describe("sanitizeBeginnerComment", () => {
  it("指標名と小数を初心者向け表示から隠す", () => {
    const text = "想定RPCIは48.6で、PAI 88.0の馬を重視。PCI3は52.1です。";
    const out = sanitizeBeginnerComment(text);
    expect(out).not.toMatch(/\b(PCI3?|RPCI|PAI)\b/i);
    expect(out).not.toMatch(/\d+\.\d+/);
    expect(out).toContain("ペース判定");
  });
});

describe("confidenceInsight", () => {
  it("高い信頼度は読みやすいにする", () => {
    const out = confidenceInsight(0.72);
    expect(out.pct).toBe(72);
    expect(out.label).toBe("読みやすい");
    expect(out.tone).toBe("strong");
    expect(out.bettingHint).toContain("中心候補");
  });

  it("中程度の信頼度は標準にする", () => {
    const out = confidenceInsight(0.55);
    expect(out.label).toBe("標準");
    expect(out.tone).toBe("normal");
  });

  it("低い信頼度は変動注意にする", () => {
    const out = confidenceInsight(0.31);
    expect(out.label).toBe("変動注意");
    expect(out.tone).toBe("caution");
    expect(out.summary).toContain("読み切りにくく");
  });

  it("パーセントは0から100に丸める", () => {
    expect(confidenceInsight(-0.1).pct).toBe(0);
    expect(confidenceInsight(1.5).pct).toBe(100);
  });
});

describe("paiBarWidth", () => {
  it("0〜100 にクランプし整数化する", () => {
    expect(paiBarWidth(-5)).toBe(0);
    expect(paiBarWidth(150)).toBe(100);
    expect(paiBarWidth(73.4)).toBe(73);
  });
});

describe("sortByPai", () => {
  it("PAI 降順に並べ、入力を破壊しない", () => {
    const input = [
      { horse_no: 1, running_style: "逃げ", pai: 50, fit_label: "中立", reasons: [] },
      { horse_no: 2, running_style: "差し", pai: 80, fit_label: "合致", reasons: [] },
    ];
    const out = sortByPai(input);
    expect(out.map((h) => h.horse_no)).toEqual([2, 1]);
    expect(input[0]?.horse_no).toBe(1);
  });
});

describe("benefitRecommendation", () => {
  it("最上位かつ適性が高い馬は軸候補にする", () => {
    const out = benefitRecommendation({ pai: 86, running_style: "先行" }, 0);
    expect(out.label).toBe("軸候補");
    expect(out.tone).toBe("main");
    expect(out.reason).toContain("好位");
  });

  it("上位の適性馬は相手候補にする", () => {
    const out = benefitRecommendation({ pai: 74, running_style: "差し" }, 2);
    expect(out.label).toBe("相手候補");
    expect(out.reason).toContain("直線");
  });

  it("順位が下でも適性があれば穴で拾うにする", () => {
    const out = benefitRecommendation({ pai: 72, running_style: "追込" }, 4);
    expect(out.label).toBe("穴で拾う");
    expect(out.tone).toBe("value");
  });

  it("適性が控えめなら押さえにする", () => {
    const out = benefitRecommendation({ pai: 58, running_style: "逃げ" }, 1);
    expect(out.label).toBe("押さえ");
    expect(out.tone).toBe("keep");
  });
});

describe("pciTone", () => {
  it("PCI を傾向に分類する（>50 スロー / <50 ハイ / =50 イーブン）", () => {
    expect(pciTone(53)).toBe("slow");
    expect(pciTone(47)).toBe("high");
    expect(pciTone(50)).toBe("even");
    expect(pciTone(null)).toBe("unknown");
    expect(pciTone(undefined)).toBe("unknown");
  });

  it("傾向ラベルを返す", () => {
    expect(pciToneLabel(pciTone(53))).toBe("スロー");
    expect(pciToneLabel(pciTone(47))).toBe("ハイ");
    expect(pciToneLabel(pciTone(null))).toBe("—");
  });
});
