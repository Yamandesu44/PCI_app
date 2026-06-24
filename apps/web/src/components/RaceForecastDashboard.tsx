import Link from "next/link";
import { Activity, BarChart3, Gauge, TrendingUp } from "lucide-react";

import { HorseFitTable } from "@/components/HorseFitTable";
import { PaceHeadline } from "@/components/PaceHeadline";
import { PaceProfileChart } from "@/components/PaceProfileChart";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { formatRaceDate, jyoName, raceNumber } from "@/lib/races";
import { benefitRecommendation, paceSpeedFromIndex, paiBarWidth, sortByPai } from "@/lib/pace";
import type { Forecast, HorseFit, RaceDetail } from "@pci/api-client";

interface RaceForecastDashboardProps {
  race: RaceDetail;
  forecast: Forecast;
}

interface StyleScore {
  key: "front" | "stalker" | "closer" | "deep";
  label: string;
  value: number;
  description: string;
}

function confidencePct(confidence: number): number {
  return Math.max(0, Math.min(100, Math.round(confidence * 100)));
}

function styleKey(style: string): StyleScore["key"] | null {
  if (style.includes("逃")) return "front";
  if (style.includes("先")) return "stalker";
  if (style.includes("差")) return "closer";
  if (style.includes("追")) return "deep";
  return null;
}

function buildStyleScores(horses: HorseFit[]): StyleScore[] {
  const base: StyleScore[] = [
    { key: "front", label: "逃げ", value: 0, description: "前半から主導権を取る馬" },
    { key: "stalker", label: "先行", value: 0, description: "好位で流れに乗る馬" },
    { key: "closer", label: "差し", value: 0, description: "中団から末脚を伸ばす馬" },
    { key: "deep", label: "追込", value: 0, description: "後方待機で直線勝負の馬" },
  ];

  for (const horse of horses) {
    const key = styleKey(horse.running_style);
    const target = base.find((item) => item.key === key);
    if (target) {
      target.value = Math.max(target.value, paiBarWidth(horse.pai));
    }
  }

  return base;
}

function horseDisplayName(horse: HorseFit): string {
  return horse.horse_name ?? `馬番 ${horse.horse_no}`;
}

function toneClass(index: number): string {
  const tones = [
    "border-slate-900 bg-slate-950 text-white",
    "border-emerald-200 bg-emerald-50 text-emerald-950",
    "border-sky-200 bg-sky-50 text-sky-950",
    "border-amber-200 bg-amber-50 text-amber-950",
    "border-rose-200 bg-rose-50 text-rose-950",
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

export function RaceForecastDashboard({ race, forecast }: RaceForecastDashboardProps) {
  const horses = forecast.horses ?? [];
  const topHorses = sortByPai(horses).slice(0, 5);
  const styleScores = buildStyleScores(horses);
  const confidence = confidencePct(forecast.confidence);
  const course = `${race.track_type}${race.distance_m}m`;
  const predictedSpeed = paceSpeedFromIndex(forecast.predicted_rpci);

  return (
    <main className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-5 py-6 md:px-8 md:py-8">
      <div className="flex items-center justify-between gap-4 text-sm text-muted-foreground">
        <Link href="/" className="font-medium text-foreground hover:underline">
          ← トップ
        </Link>
        <span className="font-mono text-xs">{race.race_key}</span>
      </div>

      <section className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm md:p-8">
        <div className="grid gap-6 lg:grid-cols-[1.35fr_0.65fr] lg:items-end">
          <div>
            <div className="mb-4 flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-700">
                {formatRaceDate(race.race_date)}
              </span>
              <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-700">
                {course}
              </span>
            </div>
            <h1 className="text-3xl font-semibold tracking-normal text-slate-950 md:text-4xl">
              {jyoName(race.jyo_cd)} {raceNumber(race.race_key)}
            </h1>
            <p className="mt-3 text-sm font-medium text-slate-500">
              {race.grade ? `${race.grade} ・ ` : ""}
              {race.race_class ? `${race.race_class} ・ ` : ""}
              {race.field_size}頭立て
            </p>
          </div>

          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
              <Activity className="h-4 w-4" />
              想定展開
            </div>
            <p className="mt-2 text-2xl font-semibold text-slate-950">{forecast.pace_label}</p>
            <p className="mt-1 text-sm text-slate-600">{forecast.scenario_headline}</p>
            <div className="mt-4 flex items-center justify-between text-sm">
              <span className="text-slate-500">展開信頼度</span>
              <span className="font-semibold text-slate-950">{confidence}%</span>
            </div>
            <Progress value={confidence} className="mt-2 bg-slate-200" />
          </div>
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4" />
              展開分析
            </CardTitle>
            <CardDescription>脚質別に、今回の流れがどれだけ向きやすいかを示します。</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-2">
            {styleScores.map((score) => (
              <div key={score.key} className="rounded-lg border border-border p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="font-semibold text-slate-950">{score.label}有利度</p>
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
            <div className="text-5xl font-semibold text-slate-950">{confidence}%</div>
            <Progress value={confidence} className="mt-4 h-3" />
            <p className="mt-4 text-sm leading-6 text-muted-foreground">{forecast.scenario_detail}</p>
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
                  馬番 {horse.horse_no} ・ {horse.running_style}
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
                  馬番 {horseNo}
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
