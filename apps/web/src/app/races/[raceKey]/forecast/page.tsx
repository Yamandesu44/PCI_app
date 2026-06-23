import { notFound } from "next/navigation";

import { RaceForecastDashboard } from "@/components/RaceForecastDashboard";
import { api } from "@/lib/api";
import { ApiError, type Forecast, type RaceDetail } from "@pci/api-client";

// 予想は実行時にバックエンドへ問い合わせる（ビルド時フェッチを避ける）。
export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ raceKey: string }>;
}

export default async function ForecastPage({ params }: PageProps) {
  const { raceKey } = await params;

  let forecast: Forecast;
  let race: RaceDetail;
  try {
    [forecast, race] = await Promise.all([api.getForecast(raceKey), api.getRaceDetail(raceKey)]);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      notFound();
    }
    throw err;
  }

  return <RaceForecastDashboard race={race} forecast={forecast} />;
}
