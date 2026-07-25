import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { RaceNavigation } from "@/lib/races";

import { MobileRaceNavigation } from "./MobileRaceNavigation";

const navigation: RaceNavigation = {
  items: [
    {
      raceKey: "2026072504020110",
      label: "10R",
      href: "/races/2026072504020110/forecast",
      isCurrent: false,
    },
    {
      raceKey: "2026072504020111",
      label: "11R",
      href: "/races/2026072504020111/forecast",
      isCurrent: true,
    },
    {
      raceKey: "2026072504020112",
      label: "12R",
      href: "/races/2026072504020112/forecast",
      isCurrent: false,
    },
  ],
  previous: {
    raceKey: "2026072504020110",
    label: "10R",
    href: "/races/2026072504020110/forecast",
    isCurrent: false,
  },
  next: {
    raceKey: "2026072504020112",
    label: "12R",
    href: "/races/2026072504020112/forecast",
    isCurrent: false,
  },
};

describe("MobileRaceNavigation", () => {
  it("現在Rと前後レースへの正規リンクを表示する", () => {
    const markup = renderToStaticMarkup(
      <MobileRaceNavigation navigation={navigation} />,
    );

    expect(markup).toContain('aria-label="同じ競馬場のレース移動"');
    expect(markup).toContain('aria-current="page"');
    expect(markup).toContain('aria-label="前のレース 10R"');
    expect(markup).toContain('aria-label="次のレース 12R"');
    expect(markup).toContain('href="/races/2026072504020112/forecast"');
  });

  it("移動情報がない場合は何も表示しない", () => {
    expect(
      renderToStaticMarkup(<MobileRaceNavigation navigation={null} />),
    ).toBe("");
  });
});
