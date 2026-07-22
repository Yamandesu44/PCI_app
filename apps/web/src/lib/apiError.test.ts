import { describe, expect, it } from "vitest";
import { ApiError, type Readiness } from "@pci/api-client";
import { describeApiError } from "./apiError";

const outdated: Readiness = {
  status: "not_ready",
  database: "schema_outdated",
  message: "データベースの更新が必要です。",
  action: "apps/api で python -m alembic upgrade head を実行してください。",
};

describe("describeApiError", () => {
  it("500発生時にreadinessの復旧手順を優先する", async () => {
    const result = await describeApiError(new ApiError(500, "failed"), async () => outdated);

    expect(result.summary).toBe("データベースの更新が必要です。");
    expect(result.action).toContain("alembic upgrade head");
  });

  it("readinessを取得できない場合は接続案内へ戻す", async () => {
    const result = await describeApiError(new ApiError(500, "failed"), async () => {
      throw new Error("offline");
    });

    expect(result.summary).toBe("APIエラー (500)");
    expect(result.action).toContain("API_BASE_URL");
  });

  it("404ではreadinessを問い合わせない", async () => {
    let called = false;
    const result = await describeApiError(new ApiError(404, "missing"), async () => {
      called = true;
      return outdated;
    });

    expect(called).toBe(false);
    expect(result.summary).toBe("APIエラー (404)");
  });
});
