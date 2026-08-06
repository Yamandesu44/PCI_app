import { ApiError, type Readiness } from "@pci/api-client";
import {
  isApiAccessTokenConfigured,
  isApiBaseUrlConfigured,
} from "./apiConfig";

export interface ApiErrorDisplay {
  summary: string;
  action: string;
}

type ReadinessLoader = () => Promise<Readiness>;

/** 設定の判定。既定は実際の環境変数を見る。テストからは差し替える。 */
export interface ApiErrorContext {
  baseUrlConfigured: boolean;
  accessTokenConfigured: boolean;
}

const CONNECTION_ACTION =
  "FastAPIバックエンド（API_BASE_URL）が起動しているか確認してください。";

const MISSING_BASE_URL_ACTION =
  "API_BASE_URL が未設定です。デプロイ先の環境変数へAPIのURLを設定してください。";

const MISSING_TOKEN_ACTION =
  "API_ACCESS_TOKEN が未設定です。APIの PUBLIC_API_TOKEN と同じ値を設定してください。";

const TOKEN_MISMATCH_ACTION =
  "APIの PUBLIC_API_TOKEN と、Web の API_ACCESS_TOKEN が同じ値か確認してください。";

export async function describeApiError(
  error: unknown,
  loadReadiness: ReadinessLoader,
  context: ApiErrorContext = {
    baseUrlConfigured: isApiBaseUrlConfigured,
    accessTokenConfigured: isApiAccessTokenConfigured,
  },
): Promise<ApiErrorDisplay> {
  const summary =
    error instanceof ApiError
      ? `APIエラー (${error.status})`
      : "APIに接続できませんでした";

  // 認証の失敗は「繋がらない」ではない。接続案内を出すと、正常に動いている
  // APIを疑わせてしまう。未設定と不一致で案内を分ける。
  if (
    error instanceof ApiError &&
    (error.status === 401 || error.status === 403)
  ) {
    return {
      summary: "APIの認証に失敗しました",
      action: context.accessTokenConfigured
        ? TOKEN_MISMATCH_ACTION
        : MISSING_TOKEN_ACTION,
    };
  }

  // 設定漏れなら、接続先が開発用フォールバック（127.0.0.1）のままの可能性が高い。
  // 「APIが起動しているか」ではなく設定を疑わせる。
  const connectionAction = context.baseUrlConfigured
    ? CONNECTION_ACTION
    : MISSING_BASE_URL_ACTION;

  if (!(error instanceof ApiError) || error.status < 500) {
    return { summary, action: connectionAction };
  }

  try {
    const readiness = await loadReadiness();
    if (readiness.status === "not_ready") {
      return {
        summary: readiness.message ?? summary,
        action: readiness.action ?? connectionAction,
      };
    }
  } catch {
    // 診断API自体が利用できない場合は、元の接続案内を維持する。
  }
  return { summary, action: connectionAction };
}
