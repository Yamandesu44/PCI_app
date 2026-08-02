import type { Formation } from "@pci/api-client";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { FormationView, MobileFormationBoard } from "./FormationView";

const formation = {
  model_version: "test",
  groups: [
    {
      key: "front",
      label: "先頭",
      horses: [
        {
          horse_no: 1,
          frame_no: 1,
          horse_name: "テスト逃げ馬",
          running_style: "逃げ",
          confidence_label: "高",
          reasons: [{ code: "front", description: "前へ行く可能性が高いです。" }],
        },
      ],
    },
    {
      key: "stalk",
      label: "好位",
      horses: [
        {
          horse_no: 2,
          frame_no: 2,
          horse_name: "テスト先行馬",
          running_style: "先行",
          confidence_label: "標準",
          reasons: [{ code: "stalk", description: "好位で運ぶ見込みです。" }],
        },
      ],
    },
    { key: "middle", label: "中団", horses: [] },
    { key: "rear", label: "後方", horses: [] },
  ],
} as Formation;

describe("MobileFormationBoard", () => {
  it("4ゾーンを同時表示し、初期状態では馬の根拠を閉じる", () => {
    const markup = renderToStaticMarkup(
      <MobileFormationBoard formation={formation} />,
    );

    expect(markup).toContain("data-mobile-formation-board");
    expect(markup.match(/data-mobile-formation-horse/g)).toHaveLength(2);
    expect(markup).toContain("先頭");
    expect(markup).toContain("好位");
    expect(markup).toContain("中団");
    expect(markup).toContain("後方");
    expect(markup).not.toContain("data-mobile-formation-detail");
    expect(markup).not.toContain("前へ行く可能性が高いです。");
  });
});

describe("FormationView", () => {
  it("PC用の馬カードと根拠表示を維持する", () => {
    const markup = renderToStaticMarkup(<FormationView formation={formation} />);

    expect(markup).toContain("隊列予想");
    expect(markup).toContain("前へ行く可能性が高いです。");
    expect(markup).toContain("好位で運ぶ見込みです。");
  });

  it("同一画面に複数表示する場合は見出しIDを分離できる", () => {
    const markup = renderToStaticMarkup(
      <FormationView formation={formation} headingId="mobile-formation-heading" />,
    );

    expect(markup).toContain('aria-labelledby="mobile-formation-heading"');
    expect(markup).toContain('id="mobile-formation-heading"');
    expect(markup).not.toContain('id="formation-heading"');
  });
});
