import { describe, expect, it } from "vitest";

import { fitTone, paceMeta, paiBarWidth, pciTone, pciToneLabel, sortByPai } from "./pace";

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
