import { describe, expect, it } from "vitest";

import { tabIndexForKey } from "./MobileTabList";

describe("tabIndexForKey", () => {
  it("左右キーで循環する", () => {
    expect(tabIndexForKey(0, "ArrowRight", 4)).toBe(1);
    expect(tabIndexForKey(3, "ArrowRight", 4)).toBe(0);
    expect(tabIndexForKey(0, "ArrowLeft", 4)).toBe(3);
  });

  it("HomeとEndで両端へ移動する", () => {
    expect(tabIndexForKey(2, "Home", 4)).toBe(0);
    expect(tabIndexForKey(1, "End", 4)).toBe(3);
  });

  it("対象外キーと空のタブ列は処理しない", () => {
    expect(tabIndexForKey(1, "Enter", 4)).toBeNull();
    expect(tabIndexForKey(0, "ArrowRight", 0)).toBeNull();
  });
});
