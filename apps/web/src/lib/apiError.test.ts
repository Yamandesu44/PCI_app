import { describe, expect, it } from "vitest";
import { ApiError, type Readiness } from "@pci/api-client";
import { describeApiError, type ApiErrorContext } from "./apiError";

const configured: ApiErrorContext = {
  baseUrlConfigured: true,
  accessTokenConfigured: true,
};
const unconfigured: ApiErrorContext = {
  baseUrlConfigured: false,
  accessTokenConfigured: false,
};

const outdated: Readiness = {
  status: "not_ready",
  database: "schema_outdated",
  message: "データベースの更新が必要です。",
  action: "apps/api で python -m alembic upgrade head を実行してください。",
};

describe("describeApiError", () => {
  it("500発生時にreadinessの復旧手順を優先する", async () => {
    const result = await describeApiError(
      new ApiError(500, "failed"),
      async () => outdated,
    );

    expect(result.summary).toBe("データベースの更新が必要です。");
    expect(result.action).toContain("alembic upgrade head");
  });

  it("readinessを取得できない場合は接続案内へ戻す", async () => {
    const result = await describeApiError(
      new ApiError(500, "failed"),
      async () => {
        throw new Error("offline");
      },
    );

    expect(result.summary).toBe("APIエラー (500)");
    expect(result.action).toContain("API_BASE_URL");
  });

  it("404ではreadinessを問い合わせない", async () => {
    let called = false;
    const result = await describeApiError(
      new ApiError(404, "missing"),
      async () => {
        called = true;
        return outdated;
      },
    );

    expect(called).toBe(false);
    expect(result.summary).toBe("APIエラー (404)");
  });

  // 認証の失敗を接続エラーとして案内すると、動いているAPIを疑うことになる。
  it("401はトークンの不一致として案内する", async () => {
    const result = await describeApiError(
      new ApiError(401, "unauthorized"),
      async () => outdated,
      configured,
    );

    expect(result.summary).toBe("APIの認証に失敗しました");
    expect(result.action).toContain("PUBLIC_API_TOKEN");
    expect(result.action).not.toContain("起動している");
  });

  it("403も認証として扱う", async () => {
    const result = await describeApiError(
      new ApiError(403, "forbidden"),
      async () => outdated,
      configured,
    );

    expect(result.summary).toBe("APIの認証に失敗しました");
  });

  it("トークン未設定なら設定を促す", async () => {
    const result = await describeApiError(
      new ApiError(401, "unauthorized"),
      async () => outdated,
      unconfigured,
    );

    expect(result.action).toContain("API_ACCESS_TOKEN が未設定");
  });

  // 設定漏れのまま本番へ出すと、接続先が開発用フォールバックのままになる。
  it("ベースURLが未設定なら設定漏れとして案内する", async () => {
    const result = await describeApiError(
      new Error("fetch failed"),
      async () => outdated,
      unconfigured,
    );

    expect(result.action).toContain("API_BASE_URL が未設定");
    expect(result.action).not.toContain("起動している");
  });

  it("ベースURLが設定済みなら従来どおり起動確認を促す", async () => {
    const result = await describeApiError(
      new Error("fetch failed"),
      async () => outdated,
      configured,
    );

    expect(result.action).toContain("起動している");
  });
});
