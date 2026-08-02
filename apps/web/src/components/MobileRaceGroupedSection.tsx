"use client";

import Link from "next/link";
import { useState, type KeyboardEvent } from "react";
import { ChevronRight } from "lucide-react";

import { tabIndexForKey } from "@/components/MobileTabList";
import { beginnerPaceLabel, raceSpotlight } from "@/lib/pace";
import {
  formatRaceDate,
  raceClassLabel,
  raceCondition,
  raceHref,
  raceNumber,
  statusLabel,
  statusTone,
} from "@/lib/races";
import type {
  RaceBoardForecast,
  RaceSummary,
} from "@pci/api-client";

export interface RaceListItem {
  race: RaceSummary;
  forecast: RaceBoardForecast | null;
}

export interface RaceVenueItemGroup {
  jyoCd: string;
  venueName: string;
  items: RaceListItem[];
}

export interface RaceDateItemGroup {
  raceDate: string;
  venues: RaceVenueItemGroup[];
}

interface MobileRaceGroupedSectionProps {
  sectionId: string;
  dateGroups: RaceDateItemGroup[];
  featured?: boolean;
}

interface MobileRaceDateGroupProps {
  sectionId: string;
  dateGroup: RaceDateItemGroup;
  featured: boolean;
}

function MobileRaceRow({
  item,
  featured,
}: {
  item: RaceListItem;
  featured: boolean;
}) {
  const { race, forecast } = item;
  const tone = statusTone(race.status);
  const spotlight = forecast
    ? raceSpotlight({
        confidence: forecast.confidence,
        fieldSize: race.field_size,
        topFitStrength: forecast.top_fit_strength,
      })
    : null;
  const showSpotlight = spotlight !== null && spotlight.tone !== "normal";

  return (
    <Link
      data-mobile-race-row
      href={raceHref(race)}
      className={[
        "grid min-h-16 grid-cols-[40px_minmax(0,1fr)_18px] items-center gap-2 border-b border-slate-200 px-1 py-2.5 last:border-b-0",
        "transition-colors active:bg-slate-100",
        featured ? "bg-emerald-50/30" : "bg-white",
      ].join(" ")}
    >
      <span
        className={[
          "flex h-10 w-10 items-center justify-center rounded-md text-xs font-bold text-white",
          tone === "confirmed" ? "bg-emerald-700" : "bg-blue-600",
        ].join(" ")}
      >
        {raceNumber(race.race_key)}
      </span>

      <span className="min-w-0">
        <span className="flex min-w-0 items-center gap-2">
          <span className="truncate text-sm font-semibold text-slate-950">
            {raceClassLabel(race)}
          </span>
          <span className="shrink-0 text-xs text-slate-500">
            {raceCondition(race)}
          </span>
        </span>
        <span className="mt-1 flex min-w-0 items-center gap-2 text-xs text-slate-500">
          <span className="shrink-0">{race.field_size}頭</span>
          {forecast ? (
            <span className="truncate">
              展開 {beginnerPaceLabel(forecast.pace_label)}
            </span>
          ) : (
            <span className="truncate">{statusLabel(race.status)}</span>
          )}
          {showSpotlight ? (
            <span className="ml-auto shrink-0 font-semibold text-amber-700">
              {spotlight.label}
            </span>
          ) : null}
        </span>
      </span>

      <ChevronRight className="h-4 w-4 text-slate-400" aria-hidden />
    </Link>
  );
}

function MobileRaceDateGroup({
  sectionId,
  dateGroup,
  featured,
}: MobileRaceDateGroupProps) {
  const [selectedVenue, setSelectedVenue] = useState(
    dateGroup.venues[0]?.jyoCd ?? "",
  );
  const activeVenue =
    dateGroup.venues.find((venue) => venue.jyoCd === selectedVenue) ??
    dateGroup.venues[0];
  const idBase = `${sectionId}-${dateGroup.raceDate}`;

  const handleVenueKeyDown = (
    event: KeyboardEvent<HTMLButtonElement>,
    currentIndex: number,
  ) => {
    const nextIndex = tabIndexForKey(currentIndex, event.key, dateGroup.venues.length);
    if (nextIndex === null) return;

    const nextVenue = dateGroup.venues[nextIndex];
    if (!nextVenue) return;

    event.preventDefault();
    setSelectedVenue(nextVenue.jyoCd);
    const tabButtons = event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>(
      '[role="tab"]',
    );
    tabButtons?.[nextIndex]?.focus();
  };

  if (!activeVenue) return null;

  return (
    <section
      data-mobile-race-list
      className="border-t border-slate-300 pt-3 md:hidden"
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="m-0 text-sm font-semibold text-slate-950">
          {formatRaceDate(dateGroup.raceDate)}
        </h3>
        <span className="text-xs font-medium text-slate-500">
          {activeVenue.items.length}R
        </span>
      </div>

      <div
        role="tablist"
        aria-label={`${formatRaceDate(dateGroup.raceDate)}の競馬場`}
        className="mb-2 grid min-h-11 grid-flow-col auto-cols-fr rounded-md bg-slate-100 p-1"
      >
        {dateGroup.venues.map((venue, index) => {
          const selected = venue.jyoCd === activeVenue.jyoCd;
          return (
            <button
              key={venue.jyoCd}
              id={`${idBase}-tab-${venue.jyoCd}`}
              data-mobile-venue-tab
              type="button"
              role="tab"
              tabIndex={selected ? 0 : -1}
              aria-selected={selected}
              aria-controls={`${idBase}-panel`}
              onClick={() => setSelectedVenue(venue.jyoCd)}
              onKeyDown={(event) => handleVenueKeyDown(event, index)}
              className={[
                "min-w-0 rounded px-2 py-2 text-xs font-semibold transition-colors",
                selected
                  ? "bg-white text-slate-950 shadow-sm"
                  : "text-slate-500 hover:text-slate-800",
              ].join(" ")}
            >
              <span className="block truncate">{venue.venueName}</span>
            </button>
          );
        })}
      </div>

      <div
        id={`${idBase}-panel`}
        role="tabpanel"
        aria-labelledby={`${idBase}-tab-${activeVenue.jyoCd}`}
        className="overflow-hidden rounded-md border border-slate-200 bg-white"
      >
        {activeVenue.items.map((item) => (
          <MobileRaceRow
            key={item.race.race_key}
            item={item}
            featured={featured}
          />
        ))}
      </div>
    </section>
  );
}

/** スマホでは開催場をタブで切り替え、選択中の1R〜12Rだけを短い行で表示する。 */
export function MobileRaceGroupedSection({
  sectionId,
  dateGroups,
  featured = false,
}: MobileRaceGroupedSectionProps) {
  return (
    <div className="space-y-4 md:hidden">
      {dateGroups.map((dateGroup) => (
        <MobileRaceDateGroup
          key={dateGroup.raceDate}
          sectionId={sectionId}
          dateGroup={dateGroup}
          featured={featured}
        />
      ))}
    </div>
  );
}
