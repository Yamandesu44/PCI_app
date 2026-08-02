"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  CalendarDays,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
} from "lucide-react";
import type { ForecastPerformancePeriod } from "@pci/api-client";

interface Props {
  /** YYYY-MM-DD 形式の開催日リスト */
  dates: string[];
  selectedDate: string | null;
  performanceDays: ForecastPerformancePeriod;
}

const WEEKDAYS = ["日", "月", "火", "水", "木", "金", "土"] as const;
// スマホの日付ストリップは選択日の前後だけを表示する（全開催日を並べると
// 遡るのに大量スライドが必要になるため）。それより前後は月カレンダーへ委ねる。
const STRIP_WINDOW_BEFORE = 4;
const STRIP_WINDOW_AFTER = 1;

function todayKey(): string {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mm}-${dd}`;
}

function toYmd(date: Date): string {
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${mm}-${dd}`;
}

function dateFromKey(key: string): Date {
  return new Date(`${key}T00:00:00`);
}

function MobileDateStrip({
  dates,
  selectedDate,
  performanceDays,
  today,
}: Props & { today: string }) {
  const scrollerRef = useRef<HTMLElement>(null);
  const selectedRef = useRef<HTMLSpanElement>(null);
  const availableDates = [...new Set(dates)].sort();
  const activeDate = selectedDate ?? availableDates.at(-1) ?? null;
  const activeIndex = activeDate ? availableDates.indexOf(activeDate) : -1;
  const windowStart = activeIndex === -1 ? 0 : Math.max(0, activeIndex - STRIP_WINDOW_BEFORE);
  const windowEnd =
    activeIndex === -1
      ? availableDates.length
      : Math.min(availableDates.length, activeIndex + STRIP_WINDOW_AFTER + 1);
  const stripDates = availableDates.slice(windowStart, windowEnd);

  useEffect(() => {
    const scroller = scrollerRef.current;
    const selected = selectedRef.current;
    if (!scroller || !selected) return;

    scroller.scrollLeft =
      selected.offsetLeft - (scroller.clientWidth - selected.clientWidth) / 2;
  }, [activeDate]);

  const active = activeDate ? dateFromKey(activeDate) : null;

  return (
    <div
      data-mobile-date-calendar
      className="min-w-0 max-w-full overflow-hidden rounded-lg border border-slate-200 bg-white p-3 shadow-sm md:hidden"
    >
      <div className="mb-2.5 flex items-center gap-2">
        <span className="flex h-8 w-8 items-center justify-center rounded-md bg-emerald-50 text-emerald-700">
          <CalendarDays className="h-4 w-4" aria-hidden />
        </span>
        <div className="min-w-0">
          <p className="m-0 text-xs font-semibold text-slate-500">開催日</p>
          <p className="m-0 mt-0.5 truncate text-sm font-semibold text-slate-950">
            {active
              ? `${active.getFullYear()}年${active.getMonth() + 1}月${active.getDate()}日（${WEEKDAYS[active.getDay()]}）`
              : "開催日がありません"}
          </p>
        </div>
      </div>

      <nav
        ref={scrollerRef}
        data-mobile-date-strip
        className="-mx-1 flex w-full min-w-0 snap-x gap-1.5 overflow-x-auto px-1 pb-1"
        aria-label="開催日の選択"
      >
        <span aria-hidden className="w-[calc(50%-28px)] shrink-0" />
        {stripDates.map((key) => {
          const date = dateFromKey(key);
          const isSelected = key === activeDate;
          const isToday = key === today;
          const content = (
            <>
              <span className="text-[10px] font-medium">
                {WEEKDAYS[date.getDay()]}
              </span>
              <span className="mt-0.5 text-sm font-bold tabular-nums">
                {date.getMonth() + 1}/{date.getDate()}
              </span>
            </>
          );
          const className = [
            "flex h-14 min-w-14 snap-center flex-col items-center justify-center rounded-md border text-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1",
            isSelected
              ? "border-emerald-700 bg-emerald-700 text-white shadow-sm"
              : isToday
                ? "border-blue-300 bg-blue-50 text-blue-700"
                : "border-slate-200 bg-white text-slate-600 active:bg-slate-100",
          ].join(" ");

          return isSelected ? (
            <span
              key={key}
              ref={selectedRef}
              data-mobile-date-item
              aria-current="date"
              className={className}
              aria-label={`${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日（選択中）`}
            >
              {content}
            </span>
          ) : (
            <Link
              key={key}
              data-mobile-date-item
              href={`/?date=${key}&performance_days=${performanceDays}`}
              className={className}
              aria-label={`${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日（開催日）`}
            >
              {content}
            </Link>
          );
        })}
        <span aria-hidden className="w-[calc(50%-28px)] shrink-0" />
      </nav>
    </div>
  );
}

/** 指定月のカレンダーグリッド（null = 前月の空白）を返す。*/
function calendarDays(year: number, month: number): (Date | null)[] {
  const first = new Date(year, month, 1);
  const last = new Date(year, month + 1, 0);
  const cells: (Date | null)[] = Array<null>(first.getDay()).fill(null);
  for (let d = 1; d <= last.getDate(); d++) {
    cells.push(new Date(year, month, d));
  }
  while (cells.length % 7 !== 0) cells.push(null);
  return cells;
}

export function RaceDateCalendar({ dates, selectedDate, performanceDays }: Props) {
  const dateSet = new Set(dates);
  const today = todayKey();

  // 初期月: 選択日 → 最新開催日 → 今月
  const anchor = selectedDate ?? dates.at(-1) ?? today;
  const anchorDate = new Date(anchor + "T00:00:00");

  const [year, setYear] = useState(anchorDate.getFullYear());
  const [month, setMonth] = useState(anchorDate.getMonth());
  const [showPicker, setShowPicker] = useState(false);

  const prevMonth = () => {
    if (month === 0) {
      setYear((y) => y - 1);
      setMonth(11);
    } else {
      setMonth((m) => m - 1);
    }
  };
  const nextMonth = () => {
    if (month === 11) {
      setYear((y) => y + 1);
      setMonth(0);
    } else {
      setMonth((m) => m + 1);
    }
  };
  const prevYear = () => setYear((y) => y - 1);
  const nextYear = () => setYear((y) => y + 1);

  const cells = calendarDays(year, month);
  const monthLabel = `${year}年${month + 1}月`;

  return (
    <>
      <MobileDateStrip
        dates={dates}
        selectedDate={selectedDate}
        performanceDays={performanceDays}
        today={today}
      />

      <div className="mt-2 flex justify-end md:hidden">
        <button
          type="button"
          data-mobile-date-picker-toggle
          onClick={() => setShowPicker((v) => !v)}
          aria-expanded={showPicker}
          className="flex min-h-11 items-center gap-1 rounded-md px-3 text-xs font-semibold text-emerald-700 hover:bg-emerald-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
        >
          {showPicker ? "閉じる" : "他の日程を探す"}
          <ChevronDown
            className={`h-3.5 w-3.5 transition-transform ${showPicker ? "rotate-180" : ""}`}
            aria-hidden
          />
        </button>
      </div>

      <div
        data-mobile-date-picker
        className={`${showPicker ? "mt-2 block" : "hidden"} rounded-lg border border-slate-200 bg-white p-4 shadow-sm md:mt-0 md:block`}
      >
      <div className="mb-4 flex items-center gap-2 border-b border-slate-100 pb-3">
        <span className="flex h-8 w-8 items-center justify-center rounded-md bg-emerald-50 text-emerald-700">
          <CalendarDays className="h-4 w-4" aria-hidden />
        </span>
        <div>
          <p className="m-0 text-sm font-semibold text-slate-950">開催日</p>
          <p className="m-0 mt-0.5 text-[11px] text-slate-500">日付を選択</p>
        </div>
      </div>
      {/* 年・月ナビゲーション */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-0.5">
          <button
            type="button"
            onClick={prevYear}
            className="flex h-11 w-11 items-center justify-center rounded-md border border-slate-200 text-slate-500 transition hover:bg-slate-100 hover:text-slate-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 md:h-8 md:w-8"
            aria-label="前年"
          >
            <ChevronsLeft className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={prevMonth}
            className="flex h-11 w-11 items-center justify-center rounded-md border border-slate-200 text-slate-500 transition hover:bg-slate-100 hover:text-slate-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 md:h-8 md:w-8"
            aria-label="前月"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
        </div>
        <span className="text-sm font-semibold text-slate-950">{monthLabel}</span>
        <div className="flex items-center gap-0.5">
          <button
            type="button"
            onClick={nextMonth}
            className="flex h-11 w-11 items-center justify-center rounded-md border border-slate-200 text-slate-500 transition hover:bg-slate-100 hover:text-slate-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 md:h-8 md:w-8"
            aria-label="翌月"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={nextYear}
            className="flex h-11 w-11 items-center justify-center rounded-md border border-slate-200 text-slate-500 transition hover:bg-slate-100 hover:text-slate-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 md:h-8 md:w-8"
            aria-label="翌年"
          >
            <ChevronsRight className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* 曜日ヘッダー */}
      <div className="mb-1 grid grid-cols-7 text-center text-xs font-medium text-slate-400">
        {WEEKDAYS.map((w) => (
          <div key={w}>{w}</div>
        ))}
      </div>

      {/* 日付グリッド */}
      <div className="grid grid-cols-7">
        {cells.map((date, i) => {
          if (!date) return <div key={`blank-${i}`} className="h-10" />;

          const key = toYmd(date);
          const hasRace = dateSet.has(key);
          const isSelected = key === selectedDate;
          const isToday = key === today;

          const dayNum = date.getDate();

          return (
            <div key={key} className="flex flex-col items-center py-0.5">
              {hasRace ? (
                <Link
                  href={`/?date=${key}&performance_days=${performanceDays}`}
                  className={[
                    "flex h-11 w-11 items-center justify-center rounded-full text-sm font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1 md:h-8 md:w-8",
                    isSelected
                      ? "bg-emerald-700 text-white shadow-sm"
                      : isToday
                        ? "text-blue-600 ring-2 ring-blue-500 ring-offset-1 hover:bg-slate-100"
                        : "text-slate-950 hover:bg-slate-100",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  aria-current={isSelected ? "date" : undefined}
                  aria-label={`${year}年${month + 1}月${dayNum}日（開催日）`}
                >
                  {dayNum}
                </Link>
              ) : (
                <span
                  className={[
                    "flex h-11 w-11 items-center justify-center rounded-full text-sm md:h-8 md:w-8",
                    isToday ? "font-semibold text-blue-600" : "text-slate-300",
                  ].join(" ")}
                >
                  {dayNum}
                </span>
              )}
              {/* 開催ドット */}
              <span
                className={[
                  "mt-0.5 h-1 w-1 rounded-full",
                  hasRace
                    ? isSelected
                      ? "bg-emerald-700"
                      : "bg-blue-500"
                    : "invisible",
                ].join(" ")}
              />
            </div>
          );
        })}
      </div>

      {/* 凡例 */}
      <div className="mt-3 flex flex-wrap items-center gap-4 border-t border-slate-100 pt-3 text-xs text-slate-500">
        <span className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />
          開催日あり
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-flex h-4 w-4 items-center justify-center rounded-full ring-2 ring-blue-500 ring-offset-1 text-[10px] font-semibold text-blue-600">
            今
          </span>
          本日
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-4 w-4 rounded-full bg-emerald-700" />
          選択中
        </span>
      </div>
      </div>
    </>
  );
}
