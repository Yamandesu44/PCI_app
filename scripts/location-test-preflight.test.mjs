import assert from "node:assert/strict";
import { createServer } from "node:http";
import { after, before, describe, test } from "node:test";

import {
  PreflightError,
  loadConfig,
  runPreflight,
} from "./location-test-preflight.mjs";

const USERNAME = "tester";
const PASSWORD = "location-test-password";
const API_TOKEN = "a".repeat(32);

let apiServer;
let webServer;
let apiUrl;
let webUrl;

function listen(server) {
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      resolve(`http://127.0.0.1:${address.port}`);
    });
  });
}

before(async () => {
  apiServer = createServer((request, response) => {
    if (request.url === "/ready") {
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(JSON.stringify({ status: "ready", database: "ok" }));
      return;
    }
    if (request.url === "/api/v1/races?limit=1") {
      if (request.headers.authorization !== `Bearer ${API_TOKEN}`) {
        response.writeHead(401, { "WWW-Authenticate": "Bearer" });
        response.end();
        return;
      }
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end("[]");
      return;
    }
    response.writeHead(404);
    response.end();
  });
  apiUrl = await listen(apiServer);

  webServer = createServer((request, response) => {
    const expected = `Basic ${Buffer.from(`${USERNAME}:${PASSWORD}`).toString("base64")}`;
    if (request.headers.authorization !== expected) {
      response.writeHead(401, { "WWW-Authenticate": 'Basic realm="PACE LAB beta"' });
      response.end();
      return;
    }
    response.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    response.end("<main><h1>レースボード</h1></main>");
  });
  webUrl = await listen(webServer);
});

after(async () => {
  await Promise.all([
    new Promise((resolve) => apiServer.close(resolve)),
    new Promise((resolve) => webServer.close(resolve)),
  ]);
});

function validEnv(overrides = {}) {
  return {
    LOCATION_TEST_WEB_URL: webUrl,
    LOCATION_TEST_API_URL: apiUrl,
    BETA_ACCESS_USER: USERNAME,
    BETA_ACCESS_PASSWORD: PASSWORD,
    API_ACCESS_TOKEN: API_TOKEN,
    ...overrides,
  };
}

describe("loadConfig", () => {
  test("公開用の必須設定を読み込む", () => {
    const config = loadConfig(validEnv());
    assert.equal(config.webUrl, webUrl);
    assert.equal(config.apiUrl, apiUrl);
    assert.equal(config.username, USERNAME);
  });

  test("公開URLのHTTPを拒否する", () => {
    assert.throws(
      () => loadConfig(validEnv({ LOCATION_TEST_WEB_URL: "http://example.com" })),
      /HTTPS/,
    );
  });

  test("短い共有パスワードを拒否する", () => {
    assert.throws(
      () => loadConfig(validEnv({ BETA_ACCESS_PASSWORD: "short" })),
      /16文字以上/,
    );
  });

  test("短いAPIトークンを拒否する", () => {
    assert.throws(
      () => loadConfig(validEnv({ API_ACCESS_TOKEN: "short" })),
      /32文字以上/,
    );
  });

  test("共有パスワードとトークンの使い回しを拒否する", () => {
    assert.throws(
      () => loadConfig(validEnv({ BETA_ACCESS_PASSWORD: API_TOKEN })),
      /別の値/,
    );
  });
});

describe("runPreflight", () => {
  test("認証拒否、readiness、API認証、Web表示を一括確認する", async () => {
    const logs = [];
    await runPreflight(loadConfig(validEnv()), { log: (message) => logs.push(message) });
    assert.equal(logs.filter((line) => line.startsWith("PASS ")).length, 5);
    assert.match(logs.at(-1), /合格/);
    assert.equal(logs.some((line) => line.includes(PASSWORD)), false);
    assert.equal(logs.some((line) => line.includes(API_TOKEN)), false);
  });

  test("readinessがnot_readyなら失敗する", async () => {
    const fetchImpl = async (url, init) => {
      if (String(url).endsWith("/ready")) {
        return new Response(JSON.stringify({ status: "not_ready", database: "unavailable" }), {
          status: 503,
          headers: { "Content-Type": "application/json" },
        });
      }
      return fetch(url, init);
    };
    await assert.rejects(
      runPreflight(loadConfig(validEnv()), { fetchImpl, log: () => {} }),
      (error) => error instanceof PreflightError && /readiness/.test(error.message),
    );
  });

  test("認証後WebのAPIエラー表示を検出する", async () => {
    const fetchImpl = async (url, init) => {
      const response = await fetch(url, init);
      if (
        String(url) === webUrl
        && init?.headers?.Authorization?.startsWith("Basic ")
      ) {
        return new Response(
          "<h1>レースボード</h1><p>レース一覧を取得できませんでした</p>",
          { status: 200 },
        );
      }
      return response;
    };
    await assert.rejects(
      runPreflight(loadConfig(validEnv()), { fetchImpl, log: () => {} }),
      /APIエラー表示/,
    );
  });
});
