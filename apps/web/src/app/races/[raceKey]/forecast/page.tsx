import Link from "next/link";
import { notFound } from "next/navigation";

import { HorseFitTable } from "@/components/HorseFitTable";
import { PaceHeadline } from "@/components/PaceHeadline";
import { api } from "@/lib/api";
import { ApiError, type Forecast } from "@pci/api-client";

// 予想は実行時にバックエンドへ問い合わせる（ビルド時フェッチを避ける）。
export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ raceKey: string }>;
}

export default async function ForecastPage({ params }: PageProps) {
  const { raceKey } = await params;

  let forecast: Forecast;
  try {
    forecast = await api.getForecast(raceKey);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      notFound();
    }
    throw err;
  }

  const frontRunners = forecast.front_runners ?? [];
  const horses = forecast.horses ?? [];

  return (
    <main className="container">
      <p className="breadcrumb">
        <Link href="/">← トップ</Link>
        <span className="race-key">{forecast.race_key}</span>
      </p>

      <PaceHeadline
        headline={forecast.scenario_headline}
        detail={forecast.scenario_detail}
        paceLabel={forecast.pace_label}
        predictedRpci={forecast.predicted_rpci}
        confidence={forecast.confidence}
        modelVersion={forecast.model_version}
        reasons={forecast.forecast_reasons ?? []}
      />

      {frontRunners.length > 0 ? (
        <section className="panel">
          <h3>展開を作る馬</h3>
          <ul className="chips">
            {frontRunners.map((no) => (
              <li key={no} className="chip">
                {no}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="panel">
        <h3>展開が向く馬（PAI 順）</h3>
        <HorseFitTable horses={horses} />
      </section>
    </main>
  );
}
