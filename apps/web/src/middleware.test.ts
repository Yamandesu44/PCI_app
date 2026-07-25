import { afterEach, describe, expect, it } from "vitest";
import { NextRequest } from "next/server";

import { middleware } from "@/middleware";

const originalUser = process.env.BETA_ACCESS_USER;
const originalPassword = process.env.BETA_ACCESS_PASSWORD;

function request(authorization?: string): NextRequest {
  return new NextRequest("http://localhost:3000/", {
    headers: authorization ? { Authorization: authorization } : undefined,
  });
}

function authorization(username: string, password: string): string {
  return `Basic ${btoa(`${username}:${password}`)}`;
}

afterEach(() => {
  if (originalUser === undefined) delete process.env.BETA_ACCESS_USER;
  else process.env.BETA_ACCESS_USER = originalUser;
  if (originalPassword === undefined) delete process.env.BETA_ACCESS_PASSWORD;
  else process.env.BETA_ACCESS_PASSWORD = originalPassword;
});

describe("beta access middleware", () => {
  it("共有認証が未設定ならローカル開発を許可する", () => {
    delete process.env.BETA_ACCESS_USER;
    delete process.env.BETA_ACCESS_PASSWORD;

    expect(middleware(request()).status).toBe(200);
  });

  it("片方だけ設定された場合は公開せず503にする", () => {
    process.env.BETA_ACCESS_USER = "friend";
    delete process.env.BETA_ACCESS_PASSWORD;

    expect(middleware(request()).status).toBe(503);
  });

  it("認証なしのアクセスへBasic認証を要求する", () => {
    process.env.BETA_ACCESS_USER = "friend";
    process.env.BETA_ACCESS_PASSWORD = "secret";

    const response = middleware(request());

    expect(response.status).toBe(401);
    expect(response.headers.get("www-authenticate")).toContain("Basic");
  });

  it("正しい共有資格情報を許可する", () => {
    process.env.BETA_ACCESS_USER = "friend";
    process.env.BETA_ACCESS_PASSWORD = "secret";

    expect(middleware(request(authorization("friend", "secret"))).status).toBe(200);
  });
});
