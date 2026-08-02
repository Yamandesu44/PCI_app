"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

import type { RaceNavigation } from "@/lib/races";

interface MobileRaceNavigationProps {
  navigation: RaceNavigation | null | undefined;
}

function raceNumberOnly(label: string): string {
  return label.endsWith("R") ? label.slice(0, -1) : label;
}

/** 同じ開催場のレースを、片手でも素早く行き来できるモバイル専用ナビゲーション。 */
export function MobileRaceNavigation({ navigation }: MobileRaceNavigationProps) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const currentRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const scroller = scrollerRef.current;
    const current = currentRef.current;
    if (!scroller || !current) return;

    scroller.scrollLeft =
      current.offsetLeft - (scroller.clientWidth - current.clientWidth) / 2;
  }, [navigation]);

  if (!navigation) return null;

  return (
    <nav
      aria-label="同じ競馬場のレース移動"
      className="mt-3 flex h-11 min-w-0 items-stretch gap-2 md:hidden"
    >
      {navigation.previous ? (
        <Link
          href={navigation.previous.href}
          aria-label={`前のレース ${navigation.previous.label}`}
          title={`前のレース ${navigation.previous.label}`}
          className="flex w-11 shrink-0 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-emerald-500"
        >
          <ChevronLeft className="h-5 w-5" aria-hidden />
        </Link>
      ) : (
        <span
          aria-hidden
          className="flex w-11 shrink-0 items-center justify-center rounded-md border border-slate-100 bg-slate-50 text-slate-300"
        >
          <ChevronLeft className="h-5 w-5" />
        </span>
      )}

      <div
        ref={scrollerRef}
        data-mobile-race-scroller
        className="flex min-w-0 flex-1 snap-x items-center gap-1 overflow-x-auto rounded-md border border-slate-200 bg-white px-1"
      >
        {navigation.items.map((item) =>
          item.isCurrent ? (
            <span
              key={item.raceKey}
              ref={currentRef}
              aria-current="page"
              className="flex h-9 min-w-10 snap-center items-center justify-center rounded bg-slate-950 px-2 text-xs font-bold text-white"
            >
              {raceNumberOnly(item.label)}
            </span>
          ) : (
            <Link
              key={item.raceKey}
              href={item.href}
              aria-label={`${item.label}へ移動`}
              className="flex h-9 min-w-10 snap-center items-center justify-center rounded px-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-emerald-500"
            >
              {raceNumberOnly(item.label)}
            </Link>
          ),
        )}
      </div>

      {navigation.next ? (
        <Link
          href={navigation.next.href}
          aria-label={`次のレース ${navigation.next.label}`}
          title={`次のレース ${navigation.next.label}`}
          className="flex w-11 shrink-0 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-emerald-500"
        >
          <ChevronRight className="h-5 w-5" aria-hidden />
        </Link>
      ) : (
        <span
          aria-hidden
          className="flex w-11 shrink-0 items-center justify-center rounded-md border border-slate-100 bg-slate-50 text-slate-300"
        >
          <ChevronRight className="h-5 w-5" />
        </span>
      )}
    </nav>
  );
}
