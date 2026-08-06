import { describe, expect, it } from "vitest";

import type { HorseFit } from "@pci/api-client";

import {
  beginnerPaceLabel,
  benefitRecommendation,
  confidenceInsight,
  discountRecommendation,
  fitLabelDisplay,
  fitTone,
  forecastAccuracyMeta,
  forecastDecisionChecklist,
  frameColorClass,
  horseNumberLabel,
  paceMeta,
  paceSpeedFromIndex,
  paiBarWidth,
  pciTone,
  pciToneLabel,
  raceSpotlight,
  sanitizeBeginnerComment,
  sortByPaceBenefit,
  sortByPai,
  sortDiscountCandidates,
  styleAdvantageReliabilityMeta,
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

describe("beginnerPaceLabel", () => {
  it("展開3分類を実数値なしの自然な表現へ変換する", () => {
    expect(beginnerPaceLabel("ハイ")).toBe("速い流れ");
    expect(beginnerPaceLabel("平均")).toBe("平均的な流れ");
    expect(beginnerPaceLabel("スロー")).toBe("落ち着いた流れ");
    expect(beginnerPaceLabel("不明")).toBe("判断材料が不足");
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
  it("芝はバックエンドのclassify_pace()と同じ閾値（49.7/54.0）で3段階に分類する", () => {
    expect(paceSpeedFromIndex(49.6, "芝").label).toBe("ハイ");
    expect(paceSpeedFromIndex(49.7, "芝").label).toBe("平均");
    expect(paceSpeedFromIndex(54, "芝").label).toBe("平均");
    expect(paceSpeedFromIndex(54.1, "芝").label).toBe("スロー");
  });

  it("ダートはバックエンドのclassify_pace()と同じ専用閾値（44.8/48.2）で3段階に分類する", () => {
    expect(paceSpeedFromIndex(44.7, "ダート").label).toBe("ハイ");
    expect(paceSpeedFromIndex(44.8, "ダート").label).toBe("平均");
    expect(paceSpeedFromIndex(48.2, "ダート").label).toBe("平均");
    expect(paceSpeedFromIndex(48.3, "ダート").label).toBe("スロー");
  });

  it("同じ数値でも芝とダートで異なるラベルになる（track_typeを渡さないと誤判定になる不具合の回帰テスト）", () => {
    // 実際に発生した不具合: ダートの想定RPCIがダートとしては平均域なのに、
    // track_typeを渡さず芝の閾値で判定すると「ハイ」（かなり速い流れ）と誤表示されていた。
    expect(paceSpeedFromIndex(46.5, "ダート").label).toBe("平均");
    expect(paceSpeedFromIndex(46.5, "芝").label).toBe("ハイ");
  });

  it("track_type未指定・想定外の値は芝の閾値へ安全に縮退する", () => {
    expect(paceSpeedFromIndex(49.6, null).label).toBe("ハイ");
    expect(paceSpeedFromIndex(49.6, undefined).label).toBe("ハイ");
    expect(paceSpeedFromIndex(49.6, "障害").label).toBe("ハイ");
  });

  it("null/undefinedは判定不可にする", () => {
    expect(paceSpeedFromIndex(null, "芝").label).toBe("判定不可");
    expect(paceSpeedFromIndex(undefined, "芝").symbol).toBe("-");
  });

  it("初心者向けラベルを持つ", () => {
    expect(paceSpeedFromIndex(48, "芝").beginnerLabel).toBe("速い流れ");
    expect(paceSpeedFromIndex(50, "芝").beginnerSummary).toContain("流れ");
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
      {
        horse_no: 1,
        frame_no: 1,
        running_style: "逃げ",
        pai: 50,
        fit_label: "中立",
        low_evidence: false,
        reasons: [],
      },
      {
        horse_no: 2,
        frame_no: 2,
        running_style: "差し",
        pai: 80,
        fit_label: "合致",
        low_evidence: false,
        reasons: [],
      },
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

describe("frameColorClass", () => {
  it("1〜8枠それぞれに異なる配色クラスを返す（隊列予想と同じ配色を全画面で共有する）", () => {
    const classes = [1, 2, 3, 4, 5, 6, 7, 8].map((frameNo) =>
      frameColorClass(frameNo),
    );
    expect(new Set(classes).size).toBe(8);
  });

  it("1枠は白地、2枠は黒地など、JRA公式の配色を反映する", () => {
    expect(frameColorClass(1)).toContain("bg-white");
    expect(frameColorClass(2)).toContain("bg-slate-950");
    expect(frameColorClass(3)).toContain("bg-red-600");
    expect(frameColorClass(5)).toContain("bg-yellow-400");
    expect(frameColorClass(8)).toContain("bg-pink-400");
  });

  it("枠順未確定（frame_no<=0）は色を付けず中立表示にする", () => {
    expect(frameColorClass(0)).not.toContain("bg-red");
    expect(frameColorClass(0)).not.toContain("bg-white");
    expect(frameColorClass(-1)).toBe(frameColorClass(0));
  });

  it("未定義の枠番（9以上）でも中立表示へ安全に縮退する", () => {
    expect(frameColorClass(9)).toBe(frameColorClass(0));
  });
});

describe("raceSpotlight", () => {
  it("信頼度と最上位馬の適性が高いレースを注目にする", () => {
    const out = raceSpotlight({
      confidence: 0.72,
      fieldSize: 12,
      horses: [
        {
          horse_no: 1,
          frame_no: 1,
          running_style: "先行",
          pai: 68,
          fit_label: "合致",
          low_evidence: false,
          reasons: [],
        },
      ],
    });

    expect(out).toMatchObject({ label: "注目", tone: "focus" });
  });

  it("多頭数で展開恩恵候補がいるレースを妙味にする", () => {
    const out = raceSpotlight({
      confidence: 0.58,
      fieldSize: 16,
      horses: [
        {
          horse_no: 1,
          frame_no: 1,
          running_style: "差し",
          pai: 66,
          fit_label: "合致",
          low_evidence: false,
          reasons: [],
        },
      ],
    });

    expect(out).toMatchObject({ label: "妙味", tone: "value" });
  });

  it("信頼度が低いレースを波乱注意にする", () => {
    const out = raceSpotlight({
      confidence: 0.42,
      fieldSize: 10,
      horses: [
        {
          horse_no: 1,
          frame_no: 1,
          running_style: "逃げ",
          pai: 52,
          fit_label: "中立",
          low_evidence: false,
          reasons: [],
        },
      ],
    });

    expect(out).toMatchObject({ label: "波乱注意", tone: "caution" });
  });

  it("信頼度が低い場合は多頭数でも波乱注意を優先する", () => {
    const out = raceSpotlight({
      confidence: 0.42,
      fieldSize: 16,
      horses: [
        {
          horse_no: 1,
          frame_no: 1,
          running_style: "差し",
          pai: 70,
          fit_label: "合致",
          low_evidence: false,
          reasons: [],
        },
      ],
    });

    expect(out).toMatchObject({ label: "波乱注意", tone: "caution" });
  });

  it("強い特徴がないレースは通常にする", () => {
    const out = raceSpotlight({
      confidence: 0.55,
      fieldSize: 12,
      horses: [
        {
          horse_no: 1,
          frame_no: 1,
          running_style: "追込",
          pai: 50,
          fit_label: "中立",
          low_evidence: false,
          reasons: [],
        },
      ],
    });

    expect(out).toMatchObject({ label: "通常", tone: "normal" });
  });
});

describe("benefitRecommendation", () => {
  it("最上位かつ展開が合致する馬は軸候補にする", () => {
    const out = benefitRecommendation(
      { fit_label: "合致", running_style: "先行", low_evidence: false },
      0,
    );
    expect(out.label).toBe("軸候補");
    expect(out.tone).toBe("main");
    expect(out.reason).toContain("好位");
  });

  it("上位の合致馬は相手候補にする", () => {
    const out = benefitRecommendation(
      { fit_label: "合致", running_style: "差し", low_evidence: false },
      2,
    );
    expect(out.label).toBe("相手候補");
    expect(out.reason).toContain("直線");
  });

  it("順位が下でも合致していれば穴で拾うにする", () => {
    const out = benefitRecommendation(
      { fit_label: "合致", running_style: "追込", low_evidence: false },
      4,
    );
    expect(out.label).toBe("穴で拾う");
    expect(out.tone).toBe("value");
  });

  it("合致していなければ押さえにする", () => {
    const out = benefitRecommendation(
      { fit_label: "中立", running_style: "逃げ", low_evidence: false },
      1,
    );
    expect(out.label).toBe("押さえ");
    expect(out.tone).toBe("keep");
  });
});

describe("discountRecommendation", () => {
  it("不利または低い適性の馬は評価下げにする", () => {
    const out = discountRecommendation({
      fit_label: "不利",
      pai: 42,
      running_style: "差し",
      low_evidence: false,
    });
    expect(out.label).toBe("評価下げ");
    expect(out.tone).toBe("avoid");
    expect(out.reason).toContain("直線");
  });

  it("明確な不利でない低めの馬は過信注意にする", () => {
    const out = discountRecommendation({
      fit_label: "中立",
      pai: 55,
      running_style: "逃げ",
      low_evidence: false,
    });
    expect(out.label).toBe("過信注意");
    expect(out.tone).toBe("caution");
  });
});

describe("sortDiscountCandidates", () => {
  it("不利ラベルを優先し、その中では適性指数が低い順に並べる", () => {
    const input = [
      {
        horse_no: 1,
        frame_no: 1,
        running_style: "逃げ",
        pai: 65,
        fit_label: "中立",
        low_evidence: false,
        reasons: [],
      },
      {
        horse_no: 2,
        frame_no: 2,
        running_style: "差し",
        pai: 48,
        fit_label: "不利",
        low_evidence: false,
        reasons: [],
      },
      {
        horse_no: 3,
        frame_no: 3,
        running_style: "先行",
        pai: 40,
        fit_label: "不利",
        low_evidence: false,
        reasons: [],
      },
      {
        horse_no: 4,
        frame_no: 4,
        running_style: "追込",
        pai: 38,
        fit_label: "中立",
        low_evidence: false,
        reasons: [],
      },
    ];

    expect(
      sortDiscountCandidates(input).map((horse) => horse.horse_no),
    ).toEqual([3, 2, 4, 1]);
  });
});

describe("forecastDecisionChecklist", () => {
  it("展開・恩恵を受ける脚質・注意馬・信頼度の4項目を作る", () => {
    const checklist = forecastDecisionChecklist({
      predictedRpci: 48,
      confidence: 0.72,
      trackType: "芝",
      horses: [
        {
          horse_no: 1,
          frame_no: 1,
          horse_name: "テストホース",
          running_style: "先行",
          pai: 86,
          fit_label: "合致",
          low_evidence: false,
          reasons: [],
        },
        {
          horse_no: 2,
          frame_no: 2,
          running_style: "差し",
          pai: 70,
          fit_label: "合致",
          low_evidence: false,
          reasons: [],
        },
      ],
      integratedRanking: {
        model_version: "integrated-v1",
        reasons: [],
        entries: [
          {
            rank: 1,
            horse_no: 2,
            frame_no: 2,
            horse_name: "総合一位",
            mark: "本命",
            ability_tier: "上位",
            fit_label: "合致",
            reasons: [],
          },
          {
            rank: 2,
            horse_no: 1,
            frame_no: 1,
            horse_name: "テストホース",
            mark: "対抗",
            ability_tier: "上位",
            fit_label: "合致",
            reasons: [],
          },
        ],
      },
    });

    expect(checklist).toHaveLength(4);
    expect(checklist[0]).toMatchObject({ label: "展開", value: "速い流れ" });
    // 2026-08-04: 個別馬の名指しをやめ、検証済みの脚質別有利度だけを出す。
    // PAIは脚質を符号化しているだけで、ダートでは最も好走する逃げに低い値を出す
    // （ADR-2026-08-04）。styleAdvantage 未指定なら脚質差なしと表示する。
    expect(checklist[1]).toMatchObject({ label: "恩恵を受ける脚質" });
    expect(checklist[1]?.value).toBe("脚質による差は小さい");
    expect(checklist[2]).toMatchObject({
      label: "注意馬",
      value: "大きな割引材料なし",
    });
    expect(checklist[3]).toMatchObject({
      label: "展開信頼度",
      value: "読みやすい ・ 72%",
    });
  });

  it("恩恵を受ける脚質は検証済みの脚質別有利度から取る（PAIは使わない）", () => {
    // 2026-08-04: PAIは脚質を符号化しているだけで、ダートでは最も好走する逃げ(1.41x)に
    // 低い値、最も走らない追込(0.47x)に高い値を出す（ADR-2026-08-04）。
    const checklist = forecastDecisionChecklist({
      predictedRpci: 48,
      confidence: 0.6,
      trackType: "芝",
      horses: [
        // PAIが最も高いのは追込だが、これは採用しない。
        {
          horse_no: 1,
          frame_no: 1,
          running_style: "追込",
          pai: 99,
          fit_label: "合致",
          low_evidence: false,
          reasons: [],
        },
      ],
      styleAdvantage: {
        model_version: "style-advantage-v4",
        reliability: "standard",
        reliability_reason: null,
        reasons: [],
        entries: [
          { style: "逃げ", score: 78 },
          { style: "先行", score: 64 },
          { style: "差し", score: 50 },
          { style: "追込", score: 50 },
        ],
      },
    });

    expect(checklist[1]).toMatchObject({ label: "恩恵を受ける脚質" });
    expect(checklist[1]?.value).toBe("逃げ / 先行");
    // 後方脚質は ADR-0010 により常に互角なので挙げない。
    expect(checklist[1]?.value).not.toContain("追込");
  });

  it("前付けが有利にならない流れでは脚質差なしと述べる", () => {
    const checklist = forecastDecisionChecklist({
      predictedRpci: 52,
      confidence: 0.6,
      trackType: "芝",
      horses: [],
      styleAdvantage: {
        model_version: "style-advantage-v4",
        reliability: "standard",
        reliability_reason: null,
        reasons: [],
        entries: [
          { style: "逃げ", score: 52 },
          { style: "先行", score: 50 },
        ],
      },
    });

    expect(checklist[1]?.value).toBe("脚質による差は小さい");
  });

  it("馬データがない場合も展開の項目は破綻しない", () => {
    const checklist = forecastDecisionChecklist({
      predictedRpci: null,
      confidence: 0.4,
      trackType: "芝",
      horses: [],
    });

    expect(checklist[0]?.value).toBe("判断材料が不足");
    // 脚質別有利度が無ければ「差は小さい」と述べる。個別馬を推さないので不足表示は不要。
    expect(checklist[1]?.value).toBe("脚質による差は小さい");
    expect(checklist[2]?.value).toBe("大きな割引材料なし");
    expect(checklist[3]?.value).toBe("変動注意 ・ 40%");
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
    model_version: "style-advantage-v4",
    reliability: "standard" as const,
    reliability_reason: null,
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
    expect(scores.map((s) => s.label)).toEqual([
      "逃げ",
      "先行",
      "差し",
      "追込",
    ]);
    expect(scores[0].description).toContain("主導権");
    expect(scores[3].value).toBe(33);
  });

  it("前付けのスコアを 有利/やや有利/互角/やや不利/不利 の言葉へ変換する", () => {
    const verdicts = styleAdvantageScores({
      ...advantage,
      entries: [
        { style: "逃げ", score: 72.0 },
        { style: "先行", score: 62.0 },
      ],
    }).map((s) => s.verdict);
    expect(verdicts).toEqual(["有利", "やや有利"]);

    const even = styleAdvantageScores({
      ...advantage,
      entries: [{ style: "先行", score: 50.0 }],
    });
    expect(even[0].verdict).toBe("互角");

    const unfavorable = styleAdvantageScores({
      ...advantage,
      entries: [
        { style: "先行", score: 38.0 },
        { style: "逃げ", score: 32.6 },
      ],
    }).map((s) => s.verdict);
    expect(unfavorable).toEqual(["やや不利", "不利"]);
  });

  it("差し・追込は展開から有利不利を断定しない", () => {
    // 実績検証（docs/SPEC.md §3.4）で、差し・追込は有利度スコアと好走率の
    // 関係が確認できなかった。高スコアでも「有利」と表示してはいけない。
    const scores = styleAdvantageScores({
      ...advantage,
      entries: [
        { style: "差し", score: 88.0 },
        { style: "追込", score: 12.0 },
      ],
    });

    expect(scores.map((s) => s.verdict)).toEqual([
      "展開の影響は小さい",
      "展開の影響は小さい",
    ]);
    expect(scores.every((s) => s.isDirectional)).toBe(false);
    expect(scores[0].note).toContain("決め手");
  });

  it("前付けは断定してよい脚質として印を付ける", () => {
    const scores = styleAdvantageScores({
      ...advantage,
      entries: [
        { style: "逃げ", score: 72.0 },
        { style: "先行", score: 62.0 },
      ],
    });

    expect(scores.every((s) => s.isDirectional)).toBe(true);
    expect(scores.every((s) => s.note === null)).toBe(true);
  });

  it("開催条件別の参考扱いと理由を表示用へ変換する", () => {
    const meta = styleAdvantageReliabilityMeta({
      ...advantage,
      reliability: "reference",
      reliability_reason: "小倉芝の夏開催では参考扱い",
    });

    expect(meta.isReference).toBe(true);
    expect(meta.label).toBe("参考");
    expect(meta.description).toContain("小倉芝");
  });
});

describe("fitLabelDisplay", () => {
  it("実績がある馬は注記を付けない", () => {
    const out = fitLabelDisplay({ fit_label: "中立", low_evidence: false });
    expect(out.lowEvidence).toBe(false);
    expect(out.note).toBeNull();
    expect(out.tone).toBe("neutral");
  });

  it("実績が無い馬には推定であることを添える", () => {
    const out = fitLabelDisplay({ fit_label: "中立", low_evidence: true });
    expect(out.lowEvidence).toBe(true);
    expect(out.note).toContain("脚質からの推定");
  });
});

describe("判断材料が薄い馬の扱い", () => {
  it("合致でも材料が薄ければ軸候補にしない", () => {
    const out = benefitRecommendation(
      { fit_label: "合致", running_style: "先行", low_evidence: true },
      0,
    );
    expect(out.label).not.toBe("軸候補");
    expect(out.tone).toBe("keep");
    expect(out.reason).toContain("脚質からの推定");
  });

  it("不利でも材料が薄ければ評価下げと断定しない", () => {
    const out = discountRecommendation({
      fit_label: "不利",
      pai: 42,
      running_style: "差し",
      low_evidence: true,
    });
    expect(out.label).not.toBe("評価下げ");
    expect(out.reason).toContain("決めつけられません");
  });
});

describe("sortByPaceBenefit", () => {
  function h(no: number, style: string, pai: number): HorseFit {
    return {
      horse_no: no,
      frame_no: no,
      running_style: style,
      pai,
      fit_label: "中立",
      low_evidence: false,
      reasons: [],
    };
  }

  const advantage = {
    model_version: "style-advantage-v4",
    reliability: "standard" as const,
    reasons: [],
    entries: [
      { style: "逃げ", score: 72 },
      { style: "先行", score: 64 },
      { style: "追込", score: 38 },
    ],
  };

  it("PAIが高くても、脚質が不利なら上へ来ない", () => {
    // ダートの追込は好走率0.47xだが高いPAIを取りうる（ADR-2026-08-04）。
    const sorted = sortByPaceBenefit(
      [h(1, "追込", 78), h(2, "逃げ", 52)],
      advantage,
    );

    expect(sorted.map((x) => x.horse_no)).toEqual([2, 1]);
  });

  it("同じ脚質の中ではPAI順になる", () => {
    const sorted = sortByPaceBenefit(
      [h(1, "逃げ", 48), h(2, "逃げ", 62)],
      advantage,
    );

    expect(sorted.map((x) => x.horse_no)).toEqual([2, 1]);
  });

  it("有利度が無い脚質は互角(50)として扱う", () => {
    const sorted = sortByPaceBenefit(
      [h(1, "自在", 60), h(2, "追込", 90)],
      advantage,
    );

    // 自在は有利度なし=50、追込は38。PAIが高くても追込が下。
    expect(sorted.map((x) => x.horse_no)).toEqual([1, 2]);
  });

  it("脚質有利度が無ければPAI順へ縮退する", () => {
    const sorted = sortByPaceBenefit(
      [h(1, "追込", 40), h(2, "逃げ", 70)],
      null,
    );

    expect(sorted.map((x) => x.horse_no)).toEqual([2, 1]);
  });

  it("入力配列を破壊しない", () => {
    const input = [h(1, "追込", 78), h(2, "逃げ", 52)];
    sortByPaceBenefit(input, advantage);

    expect(input.map((x) => x.horse_no)).toEqual([1, 2]);
  });
});
