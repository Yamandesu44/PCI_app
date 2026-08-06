/**
 * FastAPI バックエンドへの型付きクライアント（サーバコンポーネントから使用）。
 *
 * ベース URL は環境変数で注入し、生データ・認証情報はコードに含めない。
 * 設定の解決は `apiConfig.ts` に置き、エラー案内側からも同じ判定を使う。
 */
import { createClient } from "@pci/api-client";
import {
  apiAccessToken,
  apiBaseUrl,
  isApiBaseUrlConfigured,
} from "./apiConfig";

if (process.env.NODE_ENV === "production" && !isApiBaseUrlConfigured) {
  // 画面には接続エラーとしか出ないため、ログ側にも原因を残す。
  console.warn(
    "API_BASE_URL が未設定です。開発用の 127.0.0.1 へ接続を試みるため、" +
      "本番環境では必ず失敗します。デプロイ先の環境変数を設定してください。",
  );
}

export const api = createClient({
  baseUrl: apiBaseUrl,
  headers: apiAccessToken
    ? { Authorization: `Bearer ${apiAccessToken}` }
    : undefined,
});
