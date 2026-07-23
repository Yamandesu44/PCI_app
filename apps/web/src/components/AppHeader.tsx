import Link from "next/link";
import { Activity, BarChart3, CalendarDays, ChevronRight } from "lucide-react";

/** すべての画面で分析コンテキストと一覧への帰り道を保つ。 */
export function AppHeader() {
  return (
    <header className="sticky top-0 z-50 border-b border-slate-200/90 bg-white/95 backdrop-blur">
      <div className="mx-auto flex h-16 w-full max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link href="/" className="group flex items-center gap-3 text-slate-950 no-underline">
          <span className="flex h-9 w-9 items-center justify-center rounded-md bg-slate-950 text-white shadow-sm transition group-hover:bg-emerald-700">
            <Activity className="h-5 w-5" aria-hidden />
          </span>
          <span className="grid leading-none">
            <strong className="text-sm font-bold tracking-normal">PACE LAB</strong>
            <span className="mt-1 text-[11px] font-medium text-slate-500">競馬展開インテリジェンス</span>
          </span>
        </Link>

        <nav className="flex items-center gap-2" aria-label="メインナビゲーション">
          <Link
            href="/forecast-review"
            className="flex h-9 items-center gap-2 rounded-md px-3 text-sm font-semibold text-slate-600 transition hover:bg-slate-100 hover:text-slate-950"
          >
            <BarChart3 className="h-4 w-4" aria-hidden />
            <span className="hidden sm:inline">予想検証</span>
          </Link>
          <Link
            href="/"
            className="flex h-9 items-center gap-2 rounded-md px-3 text-sm font-semibold text-slate-600 transition hover:bg-slate-100 hover:text-slate-950"
          >
            <CalendarDays className="h-4 w-4" aria-hidden />
            <span className="hidden sm:inline">レース一覧</span>
            <ChevronRight className="hidden h-3.5 w-3.5 text-slate-400 sm:block" aria-hidden />
          </Link>
        </nav>
      </div>
    </header>
  );
}
