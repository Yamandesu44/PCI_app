"use client";

import Link from "next/link";
import { useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";

interface Props {
  /** YYYY-MM-DD 形式の開催日リスト */
  dates: string[];
  selectedDate: string | null;
}

const WEEKDAYS = ["日", "月", "火", "水", "木", "金", "土"] as const;

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

export function RaceDateCalendar({ dates, selectedDate }: Props) {
  const dateSet = new Set(dates);
  const today = todayKey();

  // 初期月: 選択日 → 最新開催日 → 今月
  const anchor = selectedDate ?? dates.at(-1) ?? today;
  const anchorDate = new Date(anchor + "T00:00:00");

  const [year, setYear] = useState(anchorDate.getFullYear());
  const [month, setMonth] = useState(anchorDate.getMonth());

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

  const cells = calendarDays(year, month);
  const monthLabel = `${year}年${month + 1}月`;

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-4 flex items-center gap-2 border-b border-slate-100 pb-3">
        <span className="flex h-8 w-8 items-center justify-center rounded-md bg-emerald-50 text-emerald-700">
          <CalendarDays className="h-4 w-4" aria-hidden />
        </span>
        <div>
          <p className="m-0 text-sm font-semibold text-slate-950">開催日</p>
          <p className="m-0 mt-0.5 text-[11px] text-slate-500">日付を選択</p>
        </div>
      </div>
      {/* 月ナビゲーション */}
      <div className="mb-3 flex items-center justify-between">
        <button
          type="button"
          onClick={prevMonth}
          className="rounded-md border border-slate-200 p-1.5 text-slate-500 transition hover:bg-slate-100 hover:text-slate-950"
          aria-label="前月"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        <span className="text-sm font-semibold text-slate-950">{monthLabel}</span>
        <button
          type="button"
          onClick={nextMonth}
          className="rounded-md border border-slate-200 p-1.5 text-slate-500 transition hover:bg-slate-100 hover:text-slate-950"
          aria-label="翌月"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
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
                  href={`/?date=${key}`}
                  className={[
                    "flex h-8 w-8 items-center justify-center rounded-full text-sm font-semibold transition",
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
                    "flex h-8 w-8 items-center justify-center rounded-full text-sm",
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
  );
}
