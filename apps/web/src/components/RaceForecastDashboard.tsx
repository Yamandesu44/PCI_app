import Link from "next/link";
import {
  Activity,
  ArrowLeft,
  BarChart3,
  Gauge,
  ListChecks,
  Sparkles,
  TrendingUp,
} from "lucide-react";

import { HorseFitTable } from "@/components/HorseFitTable";
import { FormationView } from "@/components/FormationView";
import { IntegratedRankingView } from "@/components/IntegratedRankingView";
import { PaceHeadline } from "@/components/PaceHeadline";
import { PaceProfileChart } from "@/components/PaceProfileChart";
import { ReasonList } from "@/components/ReasonList";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { formatRaceDate, jyoName, raceNumber } from "@/lib/races";
import {
  benefitRecommendation,
  confidenceInsight,
  discountRecommendation,
  forecastDecisionChecklist,
  horseNumberLabel,
  paceSpeedFromIndex,
  sanitizeBeginnerComment,
  sortDiscountCandidates,
  sortByPai,
  styleAdvantageScores,
} from "@/lib/pace";
import type { Forecast, HorseFit, RaceDetail } from "@pci/api-client";

interface RaceForecastDashboardProps {
  race: RaceDetail;
  forecast: Forecast;
}

function confidencePct(confidence: number): number {
  return Math.max(0, Math.min(100, Math.round(confidence * 100)));
}

function horseDisplayName(horse: HorseFit): string {
  return horse.horse_name ?? horseNumberLabel(horse);
}

function toneClass(index: number): string {
  const tones = [
    "border-[#111816] bg-[#111816] text-white",
    "border-emerald-200 bg-emerald-50 text-emerald-950",
    "border-sky-200 bg-sky-50 text-sky-950",
    "border-amber-200 bg-amber-50 text-amber-950",
    "border-violet-200 bg-violet-50 text-violet-950",
  ];
  return tones[index] ?? "border-border bg-card text-card-foreground";
}

function roleClass(tone: ReturnType<typeof benefitRecommendation>["tone"]): string {
  const tones = {
    main: "bg-white text-slate-950",
    partner: "bg-emerald-100 text-emerald-950",
    value: "bg-amber-100 text-amber-950",
    keep: "bg-slate-100 text-slate-700",
  };
  return tones[tone];
}

function discountClass(tone: ReturnType<typeof discountRecommendation>["tone"]): string {
  const tones = {
    avoid: "border-rose-200 bg-rose-50 text-rose-950",
    caution: "border-amber-200 bg-amber-50 text-amber-950",
  };
  return tones[tone];
}

function confidenceClass(tone: ReturnType<typeof confidenceInsight>["tone"]): string {
  const tones = {
    strong: "border-emerald-200 bg-emerald-50 text-emerald-950",
    normal: "border-sky-200 bg-sky-50 text-sky-950",
    caution: "border-amber-200 bg-amber-50 text-amber-950",
  };
  return tones[tone];
}

export function RaceForecastDashboard({ race, forecast }: RaceForecastDashboardProps) {
  const horses = forecast.horses ?? [];
  const frameNoByHorseNo = new Map(horses.map((horse) => [horse.horse_no, horse.frame_no]));
  const topHorses = sortByPai(horses).slice(0, 5);
  const discountHorses = sortDiscountCandidates(horses)
    .filter((horse) => horse.fit_label === "不利" || horse.pai < 60)
    .slice(0, 3);
  const styleScores = forecast.style_advantage
    ? styleAdvantageScores(forecast.style_advantage)
    : [];
  const confidence = confidencePct(forecast.confidence);
  const confidenceMeta = confidenceInsight(forecast.confidence);
  const course = `${race.track_type}${race.distance_m}m`;
  const predictedSpeed = paceSpeedFromIndex(forecast.predicted_rpci);
  const decisionChecklist = forecastDecisionChecklist({
    predictedRpci: forecast.predicted_rpci,
    confidence: forecast.confidence,
    horses,
  });

  return (
    <main className="mx-auto flex w-full max-w-7xl flex-col gap-7 px-4 py-6 sm:px-6 lg:px-8 lg:py-9">
      <div className="flex items-center justify-between gap-4 text-sm text-muted-foreground">
        <Link
          href="/"
          className="inline-flex items-center gap-2 font-semibold text-slate-600 transition hover:text-slate-950"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
          レース一覧
        </Link>
        <span className="hidden font-mono text-xs sm:inline">{race.race_key}</span>
      </div>

      <section className="relative overflow-hidden rounded-lg border border-[#20312b] bg-[#111816] p-6 text-white shadow-lg md:p-8">
        <span className="absolute inset-x-0 top-0 h-1 bg-emerald-500" />
        <div className="grid gap-6 lg:grid-cols-[1.35fr_0.65fr] lg:items-end">
          <div>
            <div className="mb-4 flex flex-wrap items-center gap-2">
              <span className="rounded-md border border-white/15 bg-white/5 px-3 py-1 text-xs font-semibold text-slate-200">
                {formatRaceDate(race.race_date)}
              </span>
              <span className="rounded-md border border-white/15 bg-white/5 px-3 py-1 text-xs font-semibold text-slate-200">
                {course}
              </span>
            </div>
            <p className="mb-2 text-xs font-semibold uppercase text-emerald-400">Race forecast</p>
            <h1 className="text-3xl font-semibold tracking-normal text-white md:text-4xl">
              {jyoName(race.jyo_cd)} {raceNumber(race.race_key)}
            </h1>
            <p className="mt-3 text-sm font-medium text-slate-400">
              {race.grade ? `${race.grade} ・ ` : ""}
              {race.race_class ? `${race.race_class} ・ ` : ""}
              {race.field_size}頭立て
            </p>
          </div>

          <div className="rounded-lg border border-white/10 bg-white/[0.06] p-5">
            <div className="flex items-center gap-2 text-xs font-semibold text-emerald-300">
              <Activity className="h-4 w-4" />
              想定展開
            </div>
            <p className="mt-2 text-2xl font-semibold text-white">{forecast.pace_label}</p>
            <p className="mt-1 text-sm leading-6 text-slate-300">{forecast.scenario_headline}</p>
            <div className="mt-4 flex items-center justify-between text-sm">
              <span className="text-slate-400">展開信頼度</span>
              <span className="font-semibold text-white">
                {confidenceMeta.label} ・ {confidence}%
              </span>
            </div>
            <Progress
              value={confidence}
              className="mt-2 bg-white/10"
              indicatorClassName="bg-emerald-400"
            />
          </div>
        </div>
      </section>

      <section>
        <div className="mb-4 flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-md bg-emerald-50 text-emerald-700">
            <ListChecks className="h-4 w-4" />
          </span>
          <h2 className="m-0 text-lg font-semibold tracking-normal text-slate-950">
            今回の検討サマリー
          </h2>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          {decisionChecklist.map((item) => (
            <div key={item.label} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <p className="m-0 text-xs font-semibold text-slate-500">{item.label}</p>
              <p className="m-0 mt-2 text-lg font-semibold tracking-normal text-slate-950">
                {item.value}
              </p>
              <p className="m-0 mt-2 text-sm leading-6 text-slate-600">{item.detail}</p>
            </div>
          ))}
        </div>
      </section>

      {forecast.integrated_ranking ? (
        <IntegratedRankingView ranking={forecast.integrated_ranking} />
      ) : null}

      {forecast.formation ? <FormationView formation={forecast.formation} /> : null}

      {forecast.comment ? (
        <section className="rounded-lg border border-emerald-200 bg-emerald-50/70 p-5 shadow-sm">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-emerald-700" aria-hidden />
            <h2 className="m-0 text-base font-semibold text-slate-950">この展開をやさしく解説</h2>
          </div>
          <p className="mt-3 text-sm font-bold leading-6 text-slate-950">
            {sanitizeBeginnerComment(forecast.comment.headline)}
          </p>
          {(forecast.comment.body ?? []).map((para, i) => (
            <p key={i} className="mt-2 text-sm leading-6 text-slate-700">
              {sanitizeBeginnerComment(para)}
            </p>
          ))}
          <details className="mt-4">
            <summary className="cursor-pointer text-xs font-medium text-emerald-700 hover:text-emerald-900">
              コメントの根拠
            </summary>
            <p className="mt-2 text-xs text-slate-500">生成方式: {forecast.comment.model_version}</p>
            <ReasonList reasons={forecast.comment.reasons ?? []} />
          </details>
        </section>
      ) : null}

      <section className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4" />
              展開分析
            </CardTitle>
            <CardDescription>
              脚質別に、今回の想定ペースがどれだけ向くかを示します（50=互角）。
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-2">
            {styleScores.map((score) => (
              <div key={score.key} className="rounded-lg border border-border p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="font-semibold text-slate-950">
                      {score.label}
                      <span
                        className={`ml-2 rounded px-1.5 py-0.5 text-xs font-semibold ${
                          score.value > 54
                            ? "bg-emerald-100 text-emerald-800"
                            : score.value < 46
                              ? "bg-rose-100 text-rose-800"
                              : "bg-slate-100 text-slate-600"
                        }`}
                      >
                        {score.verdict}
                      </span>
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">{score.description}</p>
                  </div>
                  <span className="font-mono text-lg font-semibold">{score.value}</span>
                </div>
                <Progress value={score.value} className="mt-3" />
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Gauge className="h-4 w-4" />
              展開信頼度
            </CardTitle>
            <CardDescription>モデルが今回の展開をどれだけ強く見ているか。</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-end justify-between gap-3">
              <div>
                <div className="text-5xl font-semibold text-slate-950">{confidence}%</div>
                <p className="mt-2 text-sm font-semibold text-slate-600">{confidenceMeta.label}</p>
              </div>
              <span
                className={`rounded-full border px-3 py-1 text-xs font-semibold ${confidenceClass(
                  confidenceMeta.tone,
                )}`}
              >
                {confidenceMeta.label}
              </span>
            </div>
            <Progress value={confidence} className="mt-4 h-3" />
            <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3">
              <p className="m-0 text-sm leading-6 text-slate-700">{confidenceMeta.summary}</p>
              <p className="m-0 mt-2 text-sm leading-6 text-slate-600">{confidenceMeta.bettingHint}</p>
            </div>
          </CardContent>
        </Card>
      </section>

      <section>
        <div className="mb-3 flex items-end justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-950">展開恩恵馬 TOP5</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              今回の流れが向く馬を、検討時の役割つきで表示します。
            </p>
          </div>
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          {topHorses.map((horse, index) => {
            const recommendation = benefitRecommendation(horse, index);
            return (
              <article
                key={horse.horse_no}
                className={`rounded-lg border p-4 shadow-sm ${toneClass(index)}`}
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="text-xs font-semibold opacity-70">#{index + 1}</span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-semibold ${roleClass(
                      recommendation.tone,
                    )}`}
                  >
                    {recommendation.label}
                  </span>
                </div>
                <h3 className="mt-4 text-xl font-semibold">{horseDisplayName(horse)}</h3>
                <p className="mt-1 text-sm opacity-80">
                  {horseNumberLabel(horse)} ・ {horse.running_style}
                </p>
                <dl className="mt-4 grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <dt className="text-xs font-semibold opacity-70">適性指数</dt>
                    <dd className="mt-1 text-2xl font-semibold">{horse.pai.toFixed(0)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs font-semibold opacity-70">評価</dt>
                    <dd className="mt-1 font-semibold">{horse.fit_label}</dd>
                  </div>
                </dl>
                <p className="mt-4 text-sm leading-6 opacity-90">{recommendation.reason}</p>
              </article>
            );
          })}
        </div>
      </section>

      <section>
        <div className="mb-3 flex items-end justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-950">評価を下げたい馬</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              今回の流れが向きにくい馬を、割引理由つきで表示します。
            </p>
          </div>
        </div>
        {discountHorses.length === 0 ? (
          <p className="rounded-lg border border-dashed border-slate-300 bg-white p-5 text-sm text-slate-500">
            展開面だけで大きく割り引きたい馬は見当たりません。
          </p>
        ) : (
          <div className="grid gap-3 md:grid-cols-3">
            {discountHorses.map((horse) => {
              const discount = discountRecommendation(horse);
              return (
                <article
                  key={horse.horse_no}
                  className={`rounded-lg border p-4 shadow-sm ${discountClass(discount.tone)}`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="rounded-full bg-white/70 px-2 py-0.5 text-xs font-semibold text-slate-900">
                      {discount.label}
                    </span>
                    <span className="text-xs font-semibold opacity-70">適性 {horse.pai.toFixed(0)}</span>
                  </div>
                  <h3 className="mt-4 text-xl font-semibold">{horseDisplayName(horse)}</h3>
                  <p className="mt-1 text-sm opacity-80">
                    {horseNumberLabel(horse)} ・ {horse.running_style} ・ {horse.fit_label}
                  </p>
                  <p className="mt-4 text-sm leading-6 opacity-90">{discount.reason}</p>
                </article>
              );
            })}
          </div>
        )}
      </section>

      <section className="grid gap-4 lg:grid-cols-[0.85fr_1.15fr]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BarChart3 className="h-4 w-4" />
              ペース分析
            </CardTitle>
            <CardDescription>想定ペースと脚質別スコアから、レースの流れを確認します。</CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <div className="rounded-lg bg-muted p-3">
                <dt className="text-muted-foreground">想定ペース</dt>
                <dd className="mt-1 text-2xl font-semibold" style={{ color: predictedSpeed.color }}>
                  {predictedSpeed.symbol} {predictedSpeed.label}
                </dd>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                  {predictedSpeed.description}
                </p>
              </div>
              <div className="rounded-lg bg-muted p-3">
                <dt className="text-muted-foreground">先導候補</dt>
                <dd className="mt-1 text-2xl font-semibold">{forecast.front_runners?.length ?? 0}頭</dd>
              </div>
            </dl>
            <div className="mt-5 flex flex-wrap gap-2">
              {(forecast.front_runners ?? []).map((horseNo) => (
                <span
                  key={horseNo}
                  className="rounded-full border border-border bg-white px-3 py-1 text-xs font-semibold"
                >
                  {horseNumberLabel({ horse_no: horseNo, frame_no: frameNoByHorseNo.get(horseNo) ?? 0 })}
                </span>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>脚質別プロファイル</CardTitle>
            <CardDescription>Rechartsで展開の偏りを可視化します。</CardDescription>
          </CardHeader>
          <CardContent>
            <PaceProfileChart data={styleScores.map(({ label, value }) => ({ style: label, value }))} />
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardContent className="p-0">
          <Accordion type="single" collapsible>
            <AccordionItem value="pci-detail" className="border-0 px-5">
              <AccordionTrigger>判定根拠データ</AccordionTrigger>
              <AccordionContent>
                <div className="grid gap-5">
                  <PaceHeadline
                    headline={forecast.scenario_headline}
                    detail={forecast.scenario_detail}
                    paceLabel={forecast.pace_label}
                    predictedRpci={forecast.predicted_rpci}
                    confidence={forecast.confidence}
                    modelVersion={forecast.model_version}
                    reasons={forecast.forecast_reasons ?? []}
                  />
                  <section className="panel">
                    <h3>各馬の展開適性</h3>
                    <HorseFitTable horses={horses} />
                  </section>
                </div>
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        </CardContent>
      </Card>
    </main>
  );
}
