/**
 * FastAPI バックエンドへの型付きクライアント（サーバコンポーネントから使用）。
 *
 * ベース URL は環境変数で注入し、生データ・認証情報はコードに含めない。
 */
import { createClient } from "@pci/api-client";

const baseUrl =
  process.env.API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://127.0.0.1:8000";
const apiAccessToken = process.env.API_ACCESS_TOKEN?.trim();

export const api = createClient({
  baseUrl,
  headers: apiAccessToken ? { Authorization: `Bearer ${apiAccessToken}` } : undefined,
});
