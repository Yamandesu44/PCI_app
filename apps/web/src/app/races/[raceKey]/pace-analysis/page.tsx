import Link from "next/link";
import { notFound } from "next/navigation";
import { Activity, ArrowLeft, BarChart3, Users } from "lucide-react";

import { CommentCard } from "@/components/CommentCard";
import { ForecastAccuracyBadge } from "@/components/ForecastAccuracyBadge";
import { MobileRaceNavigation } from "@/components/MobileRaceNavigation";
import { PaceAnalysisTable } from "@/components/PaceAnalysisTable";
import { RaceHero } from "@/components/RaceHero";
import { ReasonList } from "@/components/ReasonList";
import { api } from "@/lib/api";
import { paceSpeedFromIndex } from "@/lib/pace";
import { buildRaceNavigation, type RaceNavigation } from "@/lib/races";
import { ApiError, type PaceAnalysis, type RaceDetail } from "@pci/api-client";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ raceKey: string }>;
}

export default async function PaceAnalysisPage({ params }: PageProps) {
  const { raceKey } = await params;

  let analysis: PaceAnalysis;
  let race: RaceDetail;
  try {
    [analysis, race] = await Promise.all([
      api.getPaceAnalysis(raceKey),
      api.getRaceDetail(raceKey),
    ]);
  } catch (err) {
    if (err instanceof ApiError && (err.status === 404 || err.status === 409)) {
      notFound();
    }
    throw err;
  }

  const horses = analysis.horses ?? [];
  const resultSpeed = paceSpeedFromIndex(analysis.rpci_actual);
  const pci3Speed = paceSpeedFromIndex(analysis.pci3_actual);
  let navigation: RaceNavigation | null = null;
  try {
    const races = await api.listRaces(undefined, race.race_date);
    navigation = buildRaceNavigation(races, race.race_key);
  } catch {
    // 一覧APIが一時的に失敗しても、取得済みのレース分析は表示する。
  }

  return (
    <main className="mx-auto flex w-full max-w-7xl flex-col gap-7 px-4 py-6 sm:px-6 lg:px-8 lg:py-9">
      <div className="flex items-center justify-between gap-4 text-sm text-slate-500">
        <Link
          href="/"
          className="inline-flex items-center gap-2 font-semibold text-slate-600 transition hover:text-slate-950"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
          レース一覧
        </Link>
        <span className="hidden font-mono text-xs sm:inline">{analysis.race_key}</span>
      </div>

      <RaceHero race={race} mode="analysis" />
      <MobileRaceNavigation navigation={navigation} />

      <section>
        <div className="mb-4">
          <p className="m-0 text-xs font-semibold uppercase text-emerald-700">Race analysis</p>
          <h2 className="m-0 mt-1 text-xl font-semibold tracking-normal text-slate-950">
            レースの流れを振り返る
          </h2>
        </div>
        <dl className="grid gap-3 sm:grid-cols-3">
          {[
            {
              label: "実際の流れ",
              value: `${resultSpeed.symbol} ${resultSpeed.label}`,
              icon: <Activity className="h-4 w-4" aria-hidden />,
              tone: "bg-emerald-50 text-emerald-700",
            },
            {
              label: "上位3頭の傾向",
              value: `${pci3Speed.symbol} ${pci3Speed.label}`,
              icon: <BarChart3 className="h-4 w-4" aria-hidden />,
              tone: "bg-blue-50 text-blue-700",
            },
            {
              label: "分析対象",
              value: `${analysis.sample_size}頭`,
              icon: <Users className="h-4 w-4" aria-hidden />,
              tone: "bg-violet-50 text-violet-700",
            },
          ].map((item) => (
            <div key={item.label} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex items-center justify-between gap-3">
                <dt className="text-xs font-semibold text-slate-500">{item.label}</dt>
                <span className={`flex h-8 w-8 items-center justify-center rounded-md ${item.tone}`}>
                  {item.icon}
                </span>
              </div>
              <dd className="m-0 mt-3 text-2xl font-semibold text-slate-950">{item.value}</dd>
            </div>
          ))}
        </dl>
        <details className="mt-4 rounded-lg border border-slate-200 bg-white p-4 text-sm shadow-sm">
          <summary className="cursor-pointer font-semibold text-emerald-700">算出の根拠</summary>
          <p className="mb-0 mt-3 text-xs text-slate-500">算出方式: {analysis.formula_version}</p>
          <ReasonList reasons={analysis.reasons ?? []} />
        </details>
      </section>

      {analysis.forecast_accuracy ? (
        <ForecastAccuracyBadge accuracy={analysis.forecast_accuracy} />
      ) : null}

      {analysis.comment ? <CommentCard comment={analysis.comment} /> : null}

      <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-100 p-5">
          <h2 className="m-0 text-base font-semibold text-slate-950">各馬の走りとペース傾向</h2>
          <p className="m-0 mt-1 text-sm text-slate-500">★は上位3頭の傾向に含まれる馬です。</p>
        </div>
        <div className="overflow-x-auto p-2 sm:p-4">
          <PaceAnalysisTable horses={horses} />
        </div>
      </section>
    </main>
  );
}
