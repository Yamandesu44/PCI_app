import { describe, expect, it } from "vitest";

import {
  benefitRecommendation,
  confidenceInsight,
  discountRecommendation,
  fitTone,
  forecastAccuracyMeta,
  forecastDecisionChecklist,
  horseNumberLabel,
  paceMeta,
  paceSpeedFromIndex,
  paiBarWidth,
  pciTone,
  pciToneLabel,
  raceSpotlight,
  sanitizeBeginnerComment,
  sortDiscountCandidates,
  sortByPai,
  styleAdvantageScores,
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
      { horse_no: 1, frame_no: 1, running_style: "逃げ", pai: 50, fit_label: "中立", reasons: [] },
      { horse_no: 2, frame_no: 2, running_style: "差し", pai: 80, fit_label: "合致", reasons: [] },
    ];
    const out = sortByPai(input);
    expect(out.map((h) => h.horse_no)).toEqual([2, 1]);
    expect(input[0]?.horse_no).toBe(1);
  });
});

describe("horseNumberLabel", () => {
  it("枠順確定済み（frame_no>0）なら馬番として表示する", () => {
    expect(horseNumberLabel({ horse_no: 3, frame_no: 1 })).toBe("馬番 3");
  });

  it("枠順未確定（frame_no=0）なら確定情報と誤解されない表示にする", () => {
    const label = horseNumberLabel({ horse_no: 3, frame_no: 0 });
    expect(label).not.toBe("馬番 3");
    expect(label).toContain("3");
    expect(label).toContain("未確定");
  });
});

describe("raceSpotlight", () => {
  it("信頼度と最上位馬の適性が高いレースを注目にする", () => {
    const out = raceSpotlight({
      confidence: 0.72,
      fieldSize: 12,
      horses: [{ horse_no: 1, frame_no: 1, running_style: "先行", pai: 84, fit_label: "合う", reasons: [] }],
    });

    expect(out).toMatchObject({ label: "注目", tone: "focus" });
  });

  it("多頭数で展開恩恵候補がいるレースを妙味にする", () => {
    const out = raceSpotlight({
      confidence: 0.58,
      fieldSize: 16,
      horses: [{ horse_no: 1, frame_no: 1, running_style: "差し", pai: 74, fit_label: "合う", reasons: [] }],
    });

    expect(out).toMatchObject({ label: "妙味", tone: "value" });
  });

  it("信頼度が低いレースを波乱注意にする", () => {
    const out = raceSpotlight({
      confidence: 0.42,
      fieldSize: 10,
      horses: [{ horse_no: 1, frame_no: 1, running_style: "逃げ", pai: 66, fit_label: "中立", reasons: [] }],
    });

    expect(out).toMatchObject({ label: "波乱注意", tone: "caution" });
  });

  it("信頼度が低い場合は多頭数でも波乱注意を優先する", () => {
    const out = raceSpotlight({
      confidence: 0.42,
      fieldSize: 16,
      horses: [{ horse_no: 1, frame_no: 1, running_style: "差し", pai: 76, fit_label: "合う", reasons: [] }],
    });

    expect(out).toMatchObject({ label: "波乱注意", tone: "caution" });
  });

  it("強い特徴がないレースは通常にする", () => {
    const out = raceSpotlight({
      confidence: 0.55,
      fieldSize: 12,
      horses: [{ horse_no: 1, frame_no: 1, running_style: "追込", pai: 62, fit_label: "中立", reasons: [] }],
    });

    expect(out).toMatchObject({ label: "通常", tone: "normal" });
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

describe("discountRecommendation", () => {
  it("不利または低い適性の馬は評価下げにする", () => {
    const out = discountRecommendation({ fit_label: "不利", pai: 42, running_style: "差し" });
    expect(out.label).toBe("評価下げ");
    expect(out.tone).toBe("avoid");
    expect(out.reason).toContain("直線");
  });

  it("明確な不利でない低めの馬は過信注意にする", () => {
    const out = discountRecommendation({ fit_label: "中立", pai: 55, running_style: "逃げ" });
    expect(out.label).toBe("過信注意");
    expect(out.tone).toBe("caution");
  });
});

describe("sortDiscountCandidates", () => {
  it("不利ラベルを優先し、その中では適性指数が低い順に並べる", () => {
    const input = [
      { horse_no: 1, frame_no: 1, running_style: "逃げ", pai: 65, fit_label: "中立", reasons: [] },
      { horse_no: 2, frame_no: 2, running_style: "差し", pai: 48, fit_label: "不利", reasons: [] },
      { horse_no: 3, frame_no: 3, running_style: "先行", pai: 40, fit_label: "不利", reasons: [] },
      { horse_no: 4, frame_no: 4, running_style: "追込", pai: 38, fit_label: "中立", reasons: [] },
    ];

    expect(sortDiscountCandidates(input).map((horse) => horse.horse_no)).toEqual([3, 2, 4, 1]);
  });
});

describe("forecastDecisionChecklist", () => {
  it("展開・中心候補・検討方針の3項目を作る", () => {
    const checklist = forecastDecisionChecklist({
      predictedRpci: 48,
      confidence: 0.72,
      horses: [
        {
          horse_no: 1,
          frame_no: 1,
          horse_name: "テストホース",
          running_style: "先行",
          pai: 86,
          fit_label: "合致",
          reasons: [],
        },
        { horse_no: 2, frame_no: 2, running_style: "差し", pai: 70, fit_label: "合致", reasons: [] },
      ],
    });

    expect(checklist).toHaveLength(3);
    expect(checklist[0]).toMatchObject({ label: "展開", value: "やや速い流れ" });
    expect(checklist[1]?.value).toContain("テストホース");
    expect(checklist[2]).toMatchObject({ label: "検討方針", value: "読みやすい" });
  });

  it("馬データがない場合は中心候補を不足扱いにする", () => {
    const checklist = forecastDecisionChecklist({
      predictedRpci: null,
      confidence: 0.4,
      horses: [],
    });

    expect(checklist[0]?.value).toBe("判断材料が不足");
    expect(checklist[1]?.value).toBe("判断材料が不足");
    expect(checklist[2]?.value).toBe("変動注意");
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

describe("forecastAccuracyMeta", () => {
  it("的中時は hit トーンと肯定的な文言を返す", () => {
    const meta = forecastAccuracyMeta({
      label_hit: true,
      predicted_label: "スロー",
      actual_label: "スロー",
    });
    expect(meta.tone).toBe("hit");
    expect(meta.label).toBe("想定的中");
    expect(meta.summary).toContain("スロー");
    expect(meta.summary).toContain("一致しました");
  });

  it("外れ時は miss トーンで想定と実際の両方に言及する", () => {
    const meta = forecastAccuracyMeta({
      label_hit: false,
      predicted_label: "スロー",
      actual_label: "ハイ",
    });
    expect(meta.tone).toBe("miss");
    expect(meta.label).toBe("想定と相違");
    expect(meta.summary).toContain("スロー");
    expect(meta.summary).toContain("ハイ");
  });

  it("実数値（RPCI・誤差）を summary/label に含めない", () => {
    const meta = forecastAccuracyMeta({
      label_hit: false,
      predicted_label: "スロー",
      actual_label: "ハイ",
    });
    expect(meta.summary).not.toMatch(/\d+\.\d+/);
    expect(meta.label).not.toMatch(/\d/);
  });
});

describe("styleAdvantageScores", () => {
  const advantage = {
    model_version: "style-advantage-v1",
    entries: [
      { style: "逃げ", score: 72.0 },
      { style: "先行", score: 62.0 },
      { style: "差し", score: 38.0 },
      { style: "追込", score: 32.6 },
    ],
    reasons: [],
  };

  it("APIのエントリ順を保ち、ラベルと説明を付ける", () => {
    const scores = styleAdvantageScores(advantage);
    expect(scores.map((s) => s.label)).toEqual(["逃げ", "先行", "差し", "追込"]);
    expect(scores[0].description).toContain("主導権");
    expect(scores[3].value).toBe(33);
  });

  it("スコアを 有利/やや有利/互角/やや不利/不利 の言葉へ変換する", () => {
    const verdicts = styleAdvantageScores(advantage).map((s) => s.verdict);
    expect(verdicts).toEqual(["有利", "やや有利", "やや不利", "不利"]);
    const even = styleAdvantageScores({
      ...advantage,
      entries: [{ style: "先行", score: 50.0 }],
    });
    expect(even[0].verdict).toBe("互角");
  });
});
