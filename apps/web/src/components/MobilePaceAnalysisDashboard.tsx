"use client";

import Link from "next/link";
import { useState } from "react";
import {
  Activity,
  ArrowLeft,
  BarChart3,
  Flag,
  ListOrdered,
  MessageSquareText,
} from "lucide-react";

import { CommentCard } from "@/components/CommentCard";
import { ForecastAccuracyBadge } from "@/components/ForecastAccuracyBadge";
import { MobileRaceNavigation } from "@/components/MobileRaceNavigation";
import { MobileTabList } from "@/components/MobileTabList";
import { ReasonList } from "@/components/ReasonList";
import {
  frameColorClass,
  paceSpeedFromIndex,
  sanitizeBeginnerComment,
} from "@/lib/pace";
import {
  formatRaceDate,
  jyoName,
  raceNumber,
  type RaceNavigation,
} from "@/lib/races";
import type {
  HorsePaceAnalysis,
  PaceAnalysis,
  RaceDetail,
} from "@pci/api-client";

interface MobilePaceAnalysisDashboardProps {
  race: RaceDetail;
  analysis: PaceAnalysis;
  navigation?: RaceNavigation | null;
}

type MobileAnalysisTab = "summary" | "review" | "results";

const TABS: Array<{
  id: MobileAnalysisTab;
  label: string;
  icon: typeof Activity;
}> = [
  { id: "summary", label: "サマリー", icon: Flag },
  { id: "review", label: "振り返り", icon: MessageSquareText },
  { id: "results", label: "全馬", icon: ListOrdered },
];

function sortedHorses(horses: HorsePaceAnalysis[]): HorsePaceAnalysis[] {
  return [...horses].sort(
    (a, b) =>
      (a.finish_pos ?? Number.MAX_SAFE_INTEGER) -
        (b.finish_pos ?? Number.MAX_SAFE_INTEGER) ||
      a.horse_no - b.horse_no,
  );
}

function optionalLabel(value: string | null | undefined): string {
  return value && value.trim().length > 0 ? value : "未発表";
}

/** スマホでは各馬結果を二段の行へ圧縮し、横スクロールなしで主要情報を見せる。 */
export function MobilePaceResultRow({
  horse,
  trackType,
}: {
  horse: HorsePaceAnalysis;
  trackType: string | null | undefined;
}) {
  const speed = paceSpeedFromIndex(horse.pci, trackType);

  return (
    <article
      data-mobile-pace-result
      className={`flex min-h-16 min-w-0 items-center gap-3 border-b border-slate-100 px-3 py-2.5 last:border-b-0 ${
        horse.is_pci3_contributor ? "bg-emerald-50/70" : "bg-white"
      }`}
    >
      <span className="w-7 shrink-0 text-center text-base font-bold text-slate-950">
        {horse.finish_pos ?? "—"}
      </span>
      <span
        className={`flex h-9 min-w-9 shrink-0 items-center justify-center rounded-md border px-1 text-xs font-bold ${frameColorClass(horse.frame_no)}`}
      >
        {horse.horse_no}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <h3 className="m-0 truncate text-sm font-semibold text-slate-950">
            {horse.horse_name ?? "馬名未登録"}
          </h3>
          {horse.is_pci3_contributor ? (
            <span className="shrink-0 text-xs text-emerald-700" aria-label="上位3着">
              ★
            </span>
          ) : null}
        </div>
        <p className="m-0 mt-1 truncate text-xs text-slate-500">
          {horse.running_style ?? "脚質不明"} ・ {speed.symbol} {speed.label}
        </p>
      </div>
      <span className="shrink-0 text-right text-xs font-semibold text-slate-600">
        {horse.agari_3f_s !== null && horse.agari_3f_s !== undefined
          ? `${horse.agari_3f_s.toFixed(1)}秒`
          : "—"}
      </span>
    </article>
  );
}

export function MobilePaceAnalysisDashboard({
  race,
  analysis,
  navigation,
}: MobilePaceAnalysisDashboardProps) {
  const [activeTab, setActiveTab] = useState<MobileAnalysisTab>("summary");
  const horses = sortedHorses(analysis.horses ?? []);
  const topHorses = horses.filter((horse) => (horse.finish_pos ?? 99) <= 3);
  const resultSpeed = paceSpeedFromIndex(analysis.rpci_actual, race.track_type);
  const pci3Speed = paceSpeedFromIndex(analysis.pci3_actual, race.track_type);
  const commentHeadline = analysis.comment
    ? sanitizeBeginnerComment(analysis.comment.headline)
    : null;

  return (
    <main className="mx-auto w-full max-w-7xl px-3 pb-8 pt-3 md:hidden">
      <Link
        href="/"
        className="mb-3 inline-flex min-h-11 items-center gap-2 text-sm font-semibold text-slate-600"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden />
        レース一覧
      </Link>

      <section className="overflow-hidden rounded-lg border border-[#20312b] bg-[#111816] text-white shadow-sm">
        <div className="border-t-4 border-emerald-500 px-4 pb-4 pt-3">
          <p className="m-0 truncate text-xs font-semibold text-slate-400">
            {formatRaceDate(race.race_date)} ・ {race.track_type}
            {race.distance_m}m
            {race.grade ? ` ・ ${race.grade}` : ""}
          </p>
          <div className="mt-1 flex items-end justify-between gap-3">
            <div className="min-w-0">
              <h1 className="m-0 truncate text-xl font-semibold tracking-normal">
                {jyoName(race.jyo_cd)} {raceNumber(race.race_key)}
              </h1>
              <p className="m-0 mt-1 truncate text-xs text-slate-400">
                {race.race_class ?? `${analysis.field_size}頭立て`}
              </p>
            </div>
            <div className="shrink-0 rounded-md border border-white/10 bg-white/[0.06] px-3 py-2 text-right">
              <p className="m-0 text-[10px] font-semibold text-emerald-300">実際の流れ</p>
              <p className="m-0 mt-0.5 text-base font-semibold">
                {resultSpeed.symbol} {resultSpeed.label}
              </p>
            </div>
          </div>
          <dl className="mt-3 grid grid-cols-3 gap-px overflow-hidden rounded-md border border-white/10 bg-white/10">
            {[
              { label: "天候", value: optionalLabel(race.weather) },
              { label: "馬場", value: optionalLabel(race.track_condition) },
              { label: "分析", value: `${analysis.sample_size}頭` },
            ].map((item) => (
              <div key={item.label} className="min-w-0 bg-[#17201d] px-2 py-2">
                <dt className="text-[10px] font-semibold text-slate-400">{item.label}</dt>
                <dd className="m-0 mt-0.5 truncate text-xs font-semibold text-white">
                  {item.value}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      <MobileRaceNavigation navigation={navigation} />

      <div className="sticky top-0 z-20 -mx-3 mt-3 border-y border-slate-200 bg-white/95 px-3 py-2 shadow-sm backdrop-blur">
        <MobileTabList
          tabs={TABS}
          activeTab={activeTab}
          onTabChange={setActiveTab}
          ariaLabel="確定後分析の表示切り替え"
          tabIdPrefix="mobile-analysis-tab"
          panelIdPrefix="mobile-analysis-panel"
          columnsClassName="grid-cols-3"
        />
      </div>

      {activeTab === "summary" ? (
        <div
          id="mobile-analysis-panel-summary"
          role="tabpanel"
          aria-labelledby="mobile-analysis-tab-summary"
          className="mt-4 space-y-4"
        >
          {analysis.forecast_accuracy ? (
            <ForecastAccuracyBadge accuracy={analysis.forecast_accuracy} />
          ) : null}

          <section aria-label="上位3頭">
            <div className="mb-2 flex items-center justify-between gap-3">
              <h2 className="m-0 text-base font-semibold text-slate-950">上位3頭</h2>
              <span className="text-xs text-slate-500">レース結果</span>
            </div>
            <div className="overflow-hidden rounded-md border border-slate-200 shadow-sm">
              {topHorses.map((horse) => (
                <MobilePaceResultRow key={horse.horse_no} horse={horse} trackType={race.track_type} />
              ))}
            </div>
          </section>

          {commentHeadline ? (
            <section className="rounded-md border border-emerald-200 bg-emerald-50 p-4">
              <div className="flex items-center gap-2 text-emerald-700">
                <MessageSquareText className="h-4 w-4" aria-hidden />
                <h2 className="m-0 text-sm font-semibold">ひとことで振り返る</h2>
              </div>
              <p className="m-0 mt-2 text-sm font-semibold leading-6 text-slate-900">
                {commentHeadline}
              </p>
            </section>
          ) : null}
        </div>
      ) : null}

      {activeTab === "review" ? (
        <div
          id="mobile-analysis-panel-review"
          role="tabpanel"
          aria-labelledby="mobile-analysis-tab-review"
          className="mt-4 space-y-4"
        >
          <dl className="grid grid-cols-3 gap-2">
            {[
              {
                label: "実際の流れ",
                value: `${resultSpeed.symbol} ${resultSpeed.label}`,
                icon: Activity,
              },
              {
                label: "上位3頭",
                value: `${pci3Speed.symbol} ${pci3Speed.label}`,
                icon: BarChart3,
              },
              {
                label: "分析対象",
                value: `${analysis.sample_size}頭`,
                icon: ListOrdered,
              },
            ].map((item) => {
              const Icon = item.icon;
              return (
                <div
                  key={item.label}
                  className="min-w-0 rounded-md border border-slate-200 bg-white p-3 shadow-sm"
                >
                  <Icon className="h-4 w-4 text-emerald-700" aria-hidden />
                  <dt className="mt-2 text-[10px] font-semibold text-slate-500">
                    {item.label}
                  </dt>
                  <dd className="m-0 mt-1 truncate text-sm font-semibold text-slate-950">
                    {item.value}
                  </dd>
                </div>
              );
            })}
          </dl>

          {analysis.comment ? <CommentCard comment={analysis.comment} /> : null}

          <details className="rounded-md border border-slate-200 bg-white p-4 text-sm shadow-sm">
            <summary className="cursor-pointer font-semibold text-emerald-700">
              算出の根拠
            </summary>
            <p className="mb-0 mt-3 text-xs text-slate-500">
              算出方式: {analysis.formula_version}
            </p>
            <ReasonList reasons={analysis.reasons ?? []} />
          </details>
        </div>
      ) : null}

      {activeTab === "results" ? (
        <section
          id="mobile-analysis-panel-results"
          role="tabpanel"
          aria-labelledby="mobile-analysis-tab-results"
          className="mt-4"
        >
          <div className="mb-2 flex items-center justify-between gap-3">
            <div>
              <h2 className="m-0 text-base font-semibold text-slate-950">全馬の結果</h2>
              <p className="m-0 mt-1 text-xs text-slate-500">
                ★は上位3着。右端は上がり3Fです。
              </p>
            </div>
            <span className="shrink-0 text-xs font-semibold text-slate-500">
              {horses.length}頭
            </span>
          </div>
          <div className="overflow-hidden rounded-md border border-slate-200 shadow-sm">
            {horses.map((horse) => (
              <MobilePaceResultRow key={horse.horse_no} horse={horse} trackType={race.track_type} />
            ))}
          </div>
        </section>
      ) : null}
    </main>
  );
}
