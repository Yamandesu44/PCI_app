/**
 * PCI App API クライアント。
 *
 * 型は openapi.json から `npm run generate` で生成した schema.d.ts に由来し、
 * FastAPI のレスポンス契約とフロントエンドの型を一致させる（設計書 04 §4）。
 */
import type { components } from "./schema";

// ----- 生成スキーマ由来の公開型エイリアス -----

export type Reason = components["schemas"]["ReasonSchema"];
export type Comment = components["schemas"]["CommentSchema"];
export type HorseFit = components["schemas"]["HorseFitSchema"];
export type Formation = components["schemas"]["FormationSchema"];
export type FormationGroup = components["schemas"]["FormationGroupSchema"];
export type FormationHorse = components["schemas"]["FormationHorseSchema"];
export type Forecast = components["schemas"]["ForecastSchema"];
export type RaceDetail = components["schemas"]["RaceDetailSchema"];
export type RaceSummary = components["schemas"]["RaceSummarySchema"];
export type RaceBoardItem = components["schemas"]["RaceBoardItemSchema"];
export type RaceBoardForecast = components["schemas"]["RaceBoardForecastSchema"];
export type EntryDetail = components["schemas"]["EntryDetailSchema"];
export type PaceAnalysis = components["schemas"]["PaceAnalysisSchema"];
export type HorsePaceAnalysis = components["schemas"]["HorsePaceAnalysisSchema"];
export type ForecastAccuracy = components["schemas"]["ForecastAccuracySchema"];
export type StyleAdvantage = components["schemas"]["StyleAdvantageSchema"];
export type StyleAdvantageEntry = components["schemas"]["StyleAdvantageEntrySchema"];
export type IntegratedRanking = components["schemas"]["IntegratedRankingSchema"];
export type IntegratedEntry = components["schemas"]["IntegratedEntrySchema"];
export type IngestStatus = components["schemas"]["IngestStatusSchema"];
export type IngestFailure = components["schemas"]["IngestFailureSchema"];
export type ForecastPerformance = components["schemas"]["ForecastPerformanceSchema"];
export type ForecastPerformancePeriod =
  components["schemas"]["ForecastPerformancePeriod"];
export type ForecastPerformanceGroup =
  components["schemas"]["ForecastPerformanceGroupSchema"];
export type ForecastPerformanceTrendPoint =
  components["schemas"]["ForecastPerformanceTrendPointSchema"];
export type ForecastMiss = components["schemas"]["ForecastMissSchema"];
export type ForecastMisses = components["schemas"]["ForecastMissesSchema"];
export type ForecastPaceMatrixCell =
  components["schemas"]["ForecastPaceMatrixCellSchema"];
export type ForecastPaceMatrixRow =
  components["schemas"]["ForecastPaceMatrixRowSchema"];
export type Readiness = components["schemas"]["ReadinessSchema"];

export type { components, paths } from "./schema";

// ----- クライアント -----

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface ApiClientOptions {
  /** FastAPI のベース URL（例: http://127.0.0.1:8000）。末尾スラッシュは任意。 */
  baseUrl: string;
  /** テストや SSR でのフェッチ差し替え用。省略時はグローバル fetch。 */
  fetch?: typeof fetch;
  /** サーバー間認証など、すべてのリクエストへ付与する固定ヘッダー。 */
  headers?: HeadersInit;
}

export interface ForecastMissQuery {
  days?: ForecastPerformancePeriod;
  trackType?: "芝" | "ダート";
  predictedLabel?: "ハイ" | "平均" | "スロー";
  actualLabel?: "ハイ" | "平均" | "スロー";
  offset?: number;
  limit?: number;
}

export interface ApiClient {
  listRaces(limit?: number, date?: string): Promise<RaceSummary[]>;
  listRaceBoard(date: string): Promise<RaceBoardItem[]>;
  listRaceDates(): Promise<string[]>;
  getForecast(raceKey: string): Promise<Forecast>;
  getRaceDetail(raceKey: string): Promise<RaceDetail>;
  getPaceAnalysis(raceKey: string): Promise<PaceAnalysis>;
  getIngestStatus(): Promise<IngestStatus>;
  getForecastPerformance(days?: ForecastPerformancePeriod): Promise<ForecastPerformance>;
  getForecastMisses(query?: ForecastMissQuery): Promise<ForecastMisses>;
  getReadiness(): Promise<Readiness>;
}

export function createClient(options: ApiClientOptions): ApiClient {
  const doFetch = options.fetch ?? globalThis.fetch;
  const base = options.baseUrl.replace(/\/+$/, "");
  const requestInit: RequestInit | undefined = options.headers
    ? { headers: options.headers }
    : undefined;

  async function getJson<T>(path: string): Promise<T> {
    const res = await doFetch(`${base}${path}`, requestInit);
    if (!res.ok) {
      throw new ApiError(res.status, `GET ${path} failed with ${res.status}`);
    }
    return (await res.json()) as T;
  }

  return {
    listRaces: (limit, date) => {
      const params = new URLSearchParams();
      if (limit != null) params.set("limit", String(limit));
      if (date != null) params.set("date", date);
      const qs = params.toString();
      return getJson<RaceSummary[]>(`/api/v1/races${qs ? `?${qs}` : ""}`);
    },
    listRaceBoard: (date) => {
      const params = new URLSearchParams({ date });
      return getJson<RaceBoardItem[]>(`/api/v1/races/board?${params.toString()}`);
    },
    listRaceDates: () => getJson<string[]>("/api/v1/races/dates"),
    getForecast: (raceKey) =>
      getJson<Forecast>(`/api/v1/races/${encodeURIComponent(raceKey)}/forecast`),
    getRaceDetail: (raceKey) =>
      getJson<RaceDetail>(`/api/v1/races/${encodeURIComponent(raceKey)}`),
    getPaceAnalysis: (raceKey) =>
      getJson<PaceAnalysis>(`/api/v1/races/${encodeURIComponent(raceKey)}/pace-analysis`),
    getIngestStatus: () => getJson<IngestStatus>("/api/v1/ingest-status"),
    getForecastPerformance: (days) => {
      const params = new URLSearchParams();
      if (days != null) params.set("days", String(days));
      const qs = params.toString();
      return getJson<ForecastPerformance>(
        `/api/v1/forecast-performance${qs ? `?${qs}` : ""}`,
      );
    },
    getForecastMisses: (query) => {
      const params = new URLSearchParams();
      if (query?.days != null) params.set("days", String(query.days));
      if (query?.trackType != null) params.set("track_type", query.trackType);
      if (query?.predictedLabel != null) {
        params.set("predicted_label", query.predictedLabel);
      }
      if (query?.actualLabel != null) params.set("actual_label", query.actualLabel);
      if (query?.offset != null) params.set("offset", String(query.offset));
      if (query?.limit != null) params.set("limit", String(query.limit));
      const qs = params.toString();
      return getJson<ForecastMisses>(
        `/api/v1/forecast-performance/misses${qs ? `?${qs}` : ""}`,
      );
    },
    getReadiness: async () => {
      const path = "/ready";
      const res = await doFetch(`${base}${path}`, requestInit);
      if (res.status !== 200 && res.status !== 503) {
        throw new ApiError(res.status, `GET ${path} failed with ${res.status}`);
      }
      return (await res.json()) as Readiness;
    },
  };
}
