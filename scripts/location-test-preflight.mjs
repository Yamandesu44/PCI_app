import { pathToFileURL } from "node:url";

const DEFAULT_TIMEOUT_MS = 10_000;
const WEB_MARKER = "レースボード";
const WEB_API_ERROR_MARKERS = [
  "レース一覧を取得できませんでした",
  "APIに接続できませんでした",
  "APIエラー",
];

export class PreflightError extends Error {
  constructor(message) {
    super(message);
    this.name = "PreflightError";
  }
}

function requireValue(env, name) {
  const value = env[name]?.trim();
  if (!value) throw new PreflightError(`${name} が設定されていません。`);
  return value;
}

function normalizeBaseUrl(value, name) {
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new PreflightError(`${name} は有効なURLではありません。`);
  }

  if (url.username || url.password) {
    throw new PreflightError(`${name} に認証情報を含めないでください。`);
  }
  if (!["http:", "https:"].includes(url.protocol)) {
    throw new PreflightError(`${name} はHTTPまたはHTTPS URLである必要があります。`);
  }
  const isLocalhost = ["localhost", "127.0.0.1", "::1"].includes(url.hostname);
  if (url.protocol !== "https:" && !isLocalhost) {
    throw new PreflightError(`${name} は公開環境ではHTTPSである必要があります。`);
  }

  return url.href.replace(/\/+$/, "");
}

export function loadConfig(env = process.env) {
  const webUrl = normalizeBaseUrl(requireValue(env, "LOCATION_TEST_WEB_URL"), "LOCATION_TEST_WEB_URL");
  const apiUrl = normalizeBaseUrl(requireValue(env, "LOCATION_TEST_API_URL"), "LOCATION_TEST_API_URL");
  const username = requireValue(env, "BETA_ACCESS_USER");
  const password = requireValue(env, "BETA_ACCESS_PASSWORD");
  const apiToken = requireValue(env, "API_ACCESS_TOKEN");
  const ingestToken = env.INGEST_TOKEN?.trim();

  if (password.length < 16) {
    throw new PreflightError("BETA_ACCESS_PASSWORD は16文字以上にしてください。");
  }
  if (apiToken.length < 32) {
    throw new PreflightError("API_ACCESS_TOKEN は32文字以上にしてください。");
  }
  if (password === apiToken || (ingestToken && [password, apiToken].includes(ingestToken))) {
    throw new PreflightError("共有パスワード、APIトークン、取り込みトークンは別の値にしてください。");
  }

  return {
    webUrl,
    apiUrl,
    username,
    password,
    apiToken,
    timeoutMs: DEFAULT_TIMEOUT_MS,
  };
}

function endpoint(baseUrl, path) {
  return new URL(path.replace(/^\/+/, ""), `${baseUrl}/`).href;
}

async function request(fetchImpl, url, init, timeoutMs) {
  try {
    return await fetchImpl(url, {
      ...init,
      redirect: "manual",
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new PreflightError(`接続できませんでした: ${url} (${detail})`);
  }
}

function expectStatus(response, expected, label) {
  if (response.status !== expected) {
    throw new PreflightError(`${label}: HTTP ${expected}を期待しましたが${response.status}でした。`);
  }
}

async function expectReady(response) {
  expectStatus(response, 200, "API readiness");
  let body;
  try {
    body = await response.json();
  } catch {
    throw new PreflightError("API readiness: JSONレスポンスではありません。");
  }
  if (body?.status !== "ready" || body?.database !== "ok") {
    throw new PreflightError(
      `API readiness: status=${String(body?.status)} database=${String(body?.database)}です。`,
    );
  }
}

function basicAuthorization(username, password) {
  return `Basic ${Buffer.from(`${username}:${password}`, "utf8").toString("base64")}`;
}

export async function runPreflight(
  config,
  { fetchImpl = fetch, log = console.log } = {},
) {
  const pass = (message) => log(`PASS ${message}`);

  const unauthenticatedWeb = await request(
    fetchImpl,
    config.webUrl,
    { headers: { Accept: "text/html" } },
    config.timeoutMs,
  );
  expectStatus(unauthenticatedWeb, 401, "Web未認証アクセス");
  if (!unauthenticatedWeb.headers.get("www-authenticate")?.toLowerCase().startsWith("basic ")) {
    throw new PreflightError("Web未認証アクセス: Basic認証要求ヘッダーがありません。");
  }
  pass("Web未認証アクセスを401で拒否");

  const readyResponse = await request(
    fetchImpl,
    endpoint(config.apiUrl, "ready"),
    { headers: { Accept: "application/json" } },
    config.timeoutMs,
  );
  await expectReady(readyResponse);
  pass("APIとデータベースのreadiness");

  const racesUrl = endpoint(config.apiUrl, "api/v1/races?limit=1");
  const unauthenticatedApi = await request(
    fetchImpl,
    racesUrl,
    { headers: { Accept: "application/json" } },
    config.timeoutMs,
  );
  expectStatus(unauthenticatedApi, 401, "API未認証アクセス");
  if (unauthenticatedApi.headers.get("www-authenticate")?.toLowerCase() !== "bearer") {
    throw new PreflightError("API未認証アクセス: Bearer認証要求ヘッダーがありません。");
  }
  pass("API未認証アクセスを401で拒否");

  const authenticatedApi = await request(
    fetchImpl,
    racesUrl,
    {
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${config.apiToken}`,
      },
    },
    config.timeoutMs,
  );
  expectStatus(authenticatedApi, 200, "API認証アクセス");
  let races;
  try {
    races = await authenticatedApi.json();
  } catch {
    throw new PreflightError("API認証アクセス: JSONレスポンスではありません。");
  }
  if (!Array.isArray(races)) {
    throw new PreflightError("API認証アクセス: レース一覧の形式が不正です。");
  }
  pass("Bearer認証付きレース一覧API");

  const authenticatedWeb = await request(
    fetchImpl,
    config.webUrl,
    {
      headers: {
        Accept: "text/html",
        Authorization: basicAuthorization(config.username, config.password),
      },
    },
    config.timeoutMs,
  );
  expectStatus(authenticatedWeb, 200, "Web認証アクセス");
  const html = await authenticatedWeb.text();
  if (!html.includes(WEB_MARKER)) {
    throw new PreflightError(`Web認証アクセス: 「${WEB_MARKER}」を確認できません。`);
  }
  const apiErrorMarker = WEB_API_ERROR_MARKERS.find((marker) => html.includes(marker));
  if (apiErrorMarker) {
    throw new PreflightError(`Web認証アクセス: APIエラー表示「${apiErrorMarker}」を検出しました。`);
  }
  pass("共有認証付きWeb表示とWeb→API疎通");

  log("ロケテスト公開前のHTTP点検に合格しました。");
}

async function main() {
  try {
    const config = loadConfig();
    await runPreflight(config);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`FAIL ${message}`);
    process.exitCode = 1;
  }
}

const entryPoint = process.argv[1] ? pathToFileURL(process.argv[1]).href : "";
if (entryPoint === import.meta.url) {
  await main();
}
