import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { ForecastPaceMatrixRow } from "@pci/api-client";

import { ForecastErrorPattern } from "./ForecastErrorPattern";

describe("ForecastErrorPattern", () => {
  it("折りたたみ見出しに44px以上の操作領域を確保する", () => {
    const rows = [
      {
        predicted_key: "high",
        predicted_label: "速い流れ",
        sample_size: 1,
        cells: [
          { key: "high", label: "速い流れ", count: 1, rate: 1 },
        ],
      },
    ] as ForecastPaceMatrixRow[];

    const markup = renderToStaticMarkup(<ForecastErrorPattern rows={rows} />);

    expect(markup).toContain("外れ方の傾向");
    expect(markup).toContain("flex min-h-11 cursor-pointer");
  });
});
