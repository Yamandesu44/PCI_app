"use client";

import Link from "next/link";
import { useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  BarChart3,
  ChevronDown,
  Gauge,
  ListChecks,
  Route,
  Sparkles,
  Trophy,
} from "lucide-react";

import { FormationView } from "@/components/FormationView";
import { HorseFitTable } from "@/components/HorseFitTable";
import { IntegratedRankingView } from "@/components/IntegratedRankingView";
import { MobileRaceNavigation } from "@/components/MobileRaceNavigation";
import { PaceHeadline } from "@/components/PaceHeadline";
import { ReasonList } from "@/components/ReasonList";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Progress } from "@/components/ui/progress";
import {
  formatRaceDate,
  jyoName,
  raceNumber,
  type RaceNavigation,
} from "@/lib/races";
import {
  benefitRecommendation,
  confidenceInsight,
  discountRecommendation,
  forecastDecisionChecklist,
  frameColorClass,
  horseNumberLabel,
  sanitizeBeginnerComment,
  sortDiscountCandidates,
  sortByPai,
  styleAdvantageScores,
} from "@/lib/pace";
import type { Forecast, HorseFit, RaceDetail } from "@pci/api-client";

interface MobileRaceForecastDashboardProps {
  race: RaceDetail;
  forecast: Forecast;
  navigation?: RaceNavigation | null;
}

type MobileTab = "summary" | "formation" | "horses" | "detail";

const TABS: Array<{
  id: MobileTab;
  label: string;
  icon: typeof ListChecks;
}> = [
  { id: "summary", label: "サマリー", icon: ListChecks },
  { id: "formation", label: "隊列", icon: Route },
  { id: "horses", label: "注目馬", icon: Trophy },
  { id: "detail", label: "詳細", icon: BarChart3 },
];

function confidencePct(confidence: number): number {
  return Math.max(0, Math.min(100, Math.round(confidence * 100)));
}

function horseDisplayName(horse: HorseFit): string {
  return horse.horse_name ?? horseNumberLabel(horse);
}

function benefitTone(index: number): string {
  if (index === 0) return "border-slate-950 bg-slate-950 text-white";
  if (index === 1) return "border-emerald-200 bg-emerald-50 text-emerald-950";
  return "border-slate-200 bg-white text-slate-950";
}

function BenefitRow({ horse, index }: { horse: HorseFit; index: number }) {
  const recommendation = benefitRecommendation(horse, index);

  return (
    <article
      data-mobile-benefit
      className={`flex min-h-16 min-w-0 items-center gap-3 rounded-md border px-3 py-2.5 ${benefitTone(index)}`}
    >
      <span className="w-5 shrink-0 text-center text-xs font-bold opacity-70">{index + 1}</span>
      <span
        className={`flex h-9 min-w-9 shrink-0 items-center justify-center rounded-md border px-1 text-xs font-bold ${frameColorClass(horse.frame_no)}`}
      >
        {horse.frame_no > 0 ? horse.horse_no : "登録"}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <h3 className="m-0 truncate text-sm font-semibold">{horseDisplayName(horse)}</h3>
          <span className="shrink-0 rounded bg-white/70 px-1.5 py-0.5 text-[10px] font-semibold text-slate-800">
            {recommendation.label}
          </span>
        </div>
        <p className="m-0 mt-1 truncate text-xs opacity-70">
          {horseNumberLabel(horse)} ・ {horse.running_style} ・ 適性 {horse.fit_label}
        </p>
      </div>
    </article>
  );
}

interface MobileExpandableHorseRowProps {
  horse: HorseFit;
  label: string;
  reason: string;
  tone: "benefit" | "discount";
  rank?: number;
}

/** 注目馬の一覧密度を保ち、根拠は選んだ馬だけ開いて確認できるようにする。 */
export function MobileExpandableHorseRow({
  horse,
  label,
  reason,
  tone,
  rank,
}: MobileExpandableHorseRowProps) {
  const isDiscount = tone === "discount";

  return (
    <details
      data-mobile-expandable-horse
      className={`group min-w-0 overflow-hidden rounded-md border ${
        isDiscount
          ? "border-amber-200 bg-amber-50"
          : "border-slate-200 bg-white"
      }`}
    >
      <summary className="flex min-h-16 cursor-pointer list-none items-center gap-3 px-3 py-2.5 [&::-webkit-details-marker]:hidden">
        {rank ? (
          <span className="w-5 shrink-0 text-center text-xs font-bold text-slate-500">{rank}</span>
        ) : (
          <AlertTriangle className="h-4 w-5 shrink-0 text-amber-700" aria-hidden />
        )}
        <span
          className={`flex h-9 min-w-9 shrink-0 items-center justify-center rounded-md border px-1 text-xs font-bold ${frameColorClass(horse.frame_no)}`}
        >
          {horse.frame_no > 0 ? horse.horse_no : "登録"}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <h3 className="m-0 truncate text-sm font-semibold text-slate-950">
              {horseDisplayName(horse)}
            </h3>
            <span
              className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                isDiscount
                  ? "bg-amber-100 text-amber-900"
                  : "bg-slate-100 text-slate-700"
              }`}
            >
              {label}
            </span>
          </div>
          <p className="m-0 mt-1 truncate text-xs text-slate-500">
            {horseNumberLabel(horse)} ・ {horse.running_style} ・ 適性 {horse.fit_label}
          </p>
        </div>
        <ChevronDown
          className="h-4 w-4 shrink-0 text-slate-400 transition-transform group-open:rotate-180"
          aria-hidden
        />
      </summary>
      <div className="border-t border-current/10 px-4 py-3">
        <p className="m-0 text-xs font-semibold text-slate-500">今回の評価理由</p>
        <p className="m-0 mt-1 text-sm leading-6 text-slate-700">{reason}</p>
      </div>
    </details>
  );
}

export function MobileRaceForecastDashboard({
  race,
  forecast,
  navigation,
}: MobileRaceForecastDashboardProps) {
  const [activeTab, setActiveTab] = useState<MobileTab>("summary");
  const horses = forecast.horses ?? [];
  const rankedHorses = sortByPai(horses);
  const topHorses = rankedHorses.slice(0, 5);
  const discountHorses = sortDiscountCandidates(horses)
    .filter((horse) => horse.fit_label === "不利" || horse.pai < 60)
    .slice(0, 3);
  const confidence = confidencePct(forecast.confidence);
  const confidenceMeta = confidenceInsight(forecast.confidence);
  const styleScores = forecast.style_advantage
    ? styleAdvantageScores(forecast.style_advantage)
    : [];
  const decisionChecklist = forecastDecisionChecklist({
    predictedRpci: forecast.predicted_rpci,
    confidence: forecast.confidence,
    horses,
    integratedRanking: forecast.integrated_ranking,
    trackType: race.track_type,
  });

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
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="m-0 text-xs font-semibold text-slate-400">
                {formatRaceDate(race.race_date)} ・ {race.track_type}
                {race.distance_m}m
              </p>
              <h1 className="m-0 mt-1 truncate text-xl font-semibold tracking-normal">
                {jyoName(race.jyo_cd)} {raceNumber(race.race_key)}
              </h1>
              <p className="m-0 mt-1 truncate text-xs text-slate-400">
                {race.grade ? `${race.grade} ・ ` : ""}
                {race.race_class ? `${race.race_class} ・ ` : ""}
                {race.field_size}頭立て
              </p>
            </div>
            <div className="shrink-0 rounded-md border border-white/10 bg-white/[0.06] px-3 py-2 text-right">
              <p className="m-0 text-[10px] font-semibold text-emerald-300">想定展開</p>
              <p className="m-0 mt-0.5 text-base font-semibold">{forecast.pace_label}</p>
            </div>
          </div>

          <div className="mt-3 flex items-center gap-3 border-t border-white/10 pt-3">
            <Activity className="h-4 w-4 shrink-0 text-emerald-400" aria-hidden />
            <p className="m-0 min-w-0 flex-1 truncate text-sm text-slate-200">
              {forecast.scenario_headline}
            </p>
            <span className="shrink-0 text-xs font-semibold">
              {confidenceMeta.label} {confidence}%
            </span>
          </div>
          <Progress
            value={confidence}
            className="mt-2 h-1.5 bg-white/10"
            indicatorClassName="bg-emerald-400"
          />
        </div>
      </section>

      <MobileRaceNavigation navigation={navigation} />

      <div className="sticky top-0 z-20 -mx-3 mt-3 border-y border-slate-200 bg-white/95 px-3 py-2 shadow-sm backdrop-blur">
        <div
          role="tablist"
          aria-label="レース予想の表示切り替え"
          className="grid h-12 grid-cols-4 overflow-hidden rounded-md border border-slate-200 bg-slate-50"
        >
          {TABS.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                id={`mobile-tab-${tab.id}`}
                type="button"
                role="tab"
                aria-selected={isActive}
                aria-controls={`mobile-panel-${tab.id}`}
                onClick={() => setActiveTab(tab.id)}
                className={`flex min-w-0 flex-col items-center justify-center gap-0.5 border-r border-slate-200 text-[11px] font-semibold last:border-r-0 ${
                  isActive
                    ? "bg-slate-950 text-white"
                    : "bg-white text-slate-500"
                }`}
              >
                <Icon className="h-4 w-4" aria-hidden />
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>

      <div
        id={`mobile-panel-${activeTab}`}
        role="tabpanel"
        aria-labelledby={`mobile-tab-${activeTab}`}
        className="mt-4 min-w-0"
      >
        {activeTab === "summary" ? (
          <div className="grid min-w-0 gap-4">
            <section className="min-w-0" aria-labelledby="mobile-benefit-heading">
              <div className="mb-2 flex items-center justify-between gap-3">
                <h2 id="mobile-benefit-heading" className="m-0 text-base font-semibold text-slate-950">
                  展開恩恵馬 TOP3
                </h2>
                <span className="text-xs text-slate-500">まず見る3頭</span>
              </div>
              <div className="grid min-w-0 gap-2">
                {topHorses.slice(0, 3).map((horse, index) => (
                  <BenefitRow key={horse.horse_no} horse={horse} index={index} />
                ))}
              </div>
            </section>

            {forecast.comment ? (
              <section className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
                <div className="flex items-center gap-2 text-emerald-800">
                  <Sparkles className="h-4 w-4" aria-hidden />
                  <h2 className="m-0 text-sm font-semibold">この展開をひとことで</h2>
                </div>
                <p className="m-0 mt-2 text-sm font-semibold leading-6 text-slate-900">
                  {sanitizeBeginnerComment(forecast.comment.headline)}
                </p>
              </section>
            ) : null}

            <section className="min-w-0" aria-labelledby="mobile-discount-heading">
              <h2 id="mobile-discount-heading" className="m-0 mb-2 text-base font-semibold text-slate-950">
                評価を下げたい馬
              </h2>
              {discountHorses.length === 0 ? (
                <p className="m-0 rounded-lg border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-500">
                  展開面だけで大きく割り引きたい馬は見当たりません。
                </p>
              ) : (
                <div className="rounded-lg border border-amber-200 bg-amber-50">
                  {(() => {
                    const horse = discountHorses[0];
                    const discount = discountRecommendation(horse);
                    return (
                      <div className="flex min-h-16 items-center gap-3 px-3 py-2.5">
                        <AlertTriangle className="h-4 w-4 shrink-0 text-amber-700" aria-hidden />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center justify-between gap-2">
                            <h3 className="m-0 truncate text-sm font-semibold text-slate-950">
                              {horseDisplayName(horse)}
                            </h3>
                            <span className="shrink-0 text-[10px] font-semibold text-amber-800">
                              {discount.label}
                            </span>
                          </div>
                          <p className="m-0 mt-1 truncate text-xs text-slate-600">{discount.reason}</p>
                        </div>
                      </div>
                    );
                  })()}
                </div>
              )}
            </section>

            <button
              type="button"
              onClick={() => setActiveTab("horses")}
              className="flex min-h-11 items-center justify-center gap-2 rounded-md border border-slate-300 bg-white text-sm font-semibold text-slate-800"
            >
              全ての注目馬を見る
              <ChevronDown className="h-4 w-4 -rotate-90" aria-hidden />
            </button>
          </div>
        ) : null}

        {activeTab === "formation" ? (
          forecast.formation ? (
            <FormationView formation={forecast.formation} />
          ) : (
            <div className="rounded-lg border border-dashed border-slate-300 bg-white p-5 text-sm text-slate-500">
              隊列予想は枠順確定後に表示されます。
            </div>
          )
        ) : null}

        {activeTab === "horses" ? (
          <div className="grid gap-5">
            {forecast.integrated_ranking ? (
              <IntegratedRankingView ranking={forecast.integrated_ranking} />
            ) : null}

            <section aria-labelledby="mobile-all-benefit-heading">
              <h2 id="mobile-all-benefit-heading" className="m-0 mb-2 text-base font-semibold text-slate-950">
                展開恩恵馬 TOP5
              </h2>
              <div className="grid gap-2">
                {topHorses.map((horse, index) => {
                  const recommendation = benefitRecommendation(horse, index);
                  return (
                    <MobileExpandableHorseRow
                      key={horse.horse_no}
                      horse={horse}
                      rank={index + 1}
                      label={recommendation.label}
                      reason={recommendation.reason}
                      tone="benefit"
                    />
                  );
                })}
              </div>
            </section>

            <section aria-labelledby="mobile-all-discount-heading">
              <h2 id="mobile-all-discount-heading" className="m-0 mb-2 text-base font-semibold text-slate-950">
                評価を下げたい馬
              </h2>
              <div className="grid gap-2">
                {discountHorses.map((horse) => {
                  const discount = discountRecommendation(horse);
                  return (
                    <MobileExpandableHorseRow
                      key={horse.horse_no}
                      horse={horse}
                      label={discount.label}
                      reason={discount.reason}
                      tone="discount"
                    />
                  );
                })}
              </div>
            </section>
          </div>
        ) : null}

        {activeTab === "detail" ? (
          <div className="grid gap-4">
            <section aria-labelledby="mobile-checklist-heading">
              <h2 id="mobile-checklist-heading" className="m-0 mb-2 text-base font-semibold text-slate-950">
                今回の検討サマリー
              </h2>
              <div className="divide-y divide-slate-200 overflow-hidden rounded-lg border border-slate-200 bg-white">
                {decisionChecklist.map((item) => (
                  <div key={item.label} className="px-4 py-3">
                    <div className="flex items-start justify-between gap-3">
                      <p className="m-0 text-xs font-semibold text-slate-500">{item.label}</p>
                      <p className="m-0 text-right text-sm font-semibold text-slate-950">{item.value}</p>
                    </div>
                    <p className="m-0 mt-1 text-xs leading-5 text-slate-600">{item.detail}</p>
                  </div>
                ))}
              </div>
            </section>

            <section className="rounded-lg border border-slate-200 bg-white p-4">
              <div className="flex items-center gap-2">
                <Gauge className="h-4 w-4 text-emerald-700" aria-hidden />
                <h2 className="m-0 text-sm font-semibold text-slate-950">脚質別の向きやすさ</h2>
              </div>
              <div className="mt-3 grid gap-3">
                {styleScores.map((score) => (
                  <div key={score.key}>
                    <div className="flex items-center justify-between gap-3 text-xs">
                      <span className="font-semibold text-slate-700">
                        {score.label} ・ {score.verdict}
                      </span>
                      {score.isDirectional ? (
                        <span className="font-mono font-semibold text-slate-600">{score.value}</span>
                      ) : null}
                    </div>
                    {score.isDirectional ? <Progress value={score.value} className="mt-1.5" /> : null}
                  </div>
                ))}
                {styleScores.some((score) => !score.isDirectional) ? (
                  <p className="m-0 text-[11px] leading-4 text-muted-foreground">
                    {styleScores.find((score) => !score.isDirectional)?.note}
                  </p>
                ) : null}
              </div>
            </section>

            {forecast.comment ? (
              <section className="rounded-lg border border-emerald-200 bg-emerald-50/70 p-4">
                <h2 className="m-0 text-sm font-semibold text-slate-950">この展開をやさしく解説</h2>
                <p className="m-0 mt-2 text-sm font-bold leading-6 text-slate-950">
                  {sanitizeBeginnerComment(forecast.comment.headline)}
                </p>
                {(forecast.comment.body ?? []).map((paragraph, index) => (
                  <p key={index} className="m-0 mt-2 text-sm leading-6 text-slate-700">
                    {sanitizeBeginnerComment(paragraph)}
                  </p>
                ))}
                <details className="mt-3">
                  <summary className="cursor-pointer text-xs font-semibold text-emerald-700">
                    コメントの根拠
                  </summary>
                  <ReasonList reasons={forecast.comment.reasons ?? []} />
                </details>
              </section>
            ) : null}

            <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
              <Accordion type="single" collapsible>
                <AccordionItem value="pci-detail" className="border-0 px-4">
                  <AccordionTrigger>判断根拠データ</AccordionTrigger>
                  <AccordionContent>
                    <div className="grid gap-4">
                      <PaceHeadline
                        headline={forecast.scenario_headline}
                        detail={forecast.scenario_detail}
                        paceLabel={forecast.pace_label}
                        predictedRpci={forecast.predicted_rpci}
                        confidence={forecast.confidence}
                        modelVersion={forecast.model_version}
                        reasons={forecast.forecast_reasons ?? []}
                        trackType={race.track_type}
                      />
                      <div className="overflow-x-auto">
                        <HorseFitTable horses={horses} />
                      </div>
                    </div>
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
            </div>
          </div>
        ) : null}
      </div>
    </main>
  );
}
