/**
 * API 接続設定の解決と、その設定漏れの検出。
 *
 * ベース URL には開発用のフォールバックがある。手元では便利だが、**本番で
 * 環境変数を入れ忘れると気付けない**のが問題だった。デプロイ先から
 * `127.0.0.1` を叩きに行き、画面には「バックエンドが起動しているか確認して
 * ください」と出る——バックエンドは動いており、設定が無いだけなのに。
 *
 * 解決した値ではなく「明示的に設定されたか」も持ち回り、案内の文面を
 * 実際の原因に合わせられるようにする（`apiError.ts`）。
 */

const LOCAL_FALLBACK_BASE_URL = "http://127.0.0.1:8000";

function trimmed(value: string | undefined): string | undefined {
  const result = value?.trim();
  return result ? result : undefined;
}

const configuredBaseUrl =
  trimmed(process.env.API_BASE_URL) ??
  trimmed(process.env.NEXT_PUBLIC_API_BASE_URL);

export const apiBaseUrl = configuredBaseUrl ?? LOCAL_FALLBACK_BASE_URL;

/** ベース URL が環境変数から与えられたか。false なら開発用フォールバック。 */
export const isApiBaseUrlConfigured = configuredBaseUrl !== undefined;

/**
 * サーバー間トークンが設定されているか。
 *
 * API 側の `PUBLIC_API_TOKEN` と食い違うと全リクエストが 401 になる。
 * 未設定と不一致は区別できないため、案内では両方に触れる。
 */
export const isApiAccessTokenConfigured =
  trimmed(process.env.API_ACCESS_TOKEN) !== undefined;

export const apiAccessToken = trimmed(process.env.API_ACCESS_TOKEN);
