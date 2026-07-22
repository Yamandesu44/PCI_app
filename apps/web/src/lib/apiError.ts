import { ApiError, type Readiness } from "@pci/api-client";

export interface ApiErrorDisplay {
  summary: string;
  action: string;
}

type ReadinessLoader = () => Promise<Readiness>;

const CONNECTION_ACTION =
  "FastAPIバックエンド（API_BASE_URL）が起動しているか確認してください。";

export async function describeApiError(
  error: unknown,
  loadReadiness: ReadinessLoader,
): Promise<ApiErrorDisplay> {
  const summary =
    error instanceof ApiError ? `APIエラー (${error.status})` : "APIに接続できませんでした";

  if (!(error instanceof ApiError) || error.status < 500) {
    return { summary, action: CONNECTION_ACTION };
  }

  try {
    const readiness = await loadReadiness();
    if (readiness.status === "not_ready") {
      return {
        summary: readiness.message ?? summary,
        action: readiness.action ?? CONNECTION_ACTION,
      };
    }
  } catch {
    // 診断API自体が利用できない場合は、元の接続案内を維持する。
  }
  return { summary, action: CONNECTION_ACTION };
}
