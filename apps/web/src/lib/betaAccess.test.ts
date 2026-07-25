import { describe, expect, it } from "vitest";

import { hasValidBetaAccess } from "@/lib/betaAccess";

function basicAuthorization(username: string, password: string): string {
  const bytes = new TextEncoder().encode(`${username}:${password}`);
  const binary = Array.from(bytes, (byte) => String.fromCharCode(byte)).join("");
  return `Basic ${btoa(binary)}`;
}

const expected = {
  username: "friend",
  password: "安全な共有パスワード",
};

describe("hasValidBetaAccess", () => {
  it("正しい共有資格情報を受け入れる", () => {
    expect(
      hasValidBetaAccess(
        basicAuthorization(expected.username, expected.password),
        expected,
      ),
    ).toBe(true);
  });

  it("パスワード中のコロンを保持する", () => {
    const credentials = { username: "friend", password: "pass:word" };
    expect(
      hasValidBetaAccess(
        basicAuthorization(credentials.username, credentials.password),
        credentials,
      ),
    ).toBe(true);
  });

  it.each([
    null,
    "",
    "Bearer token",
    "Basic !!!",
    basicAuthorization("other", expected.password),
    basicAuthorization(expected.username, "wrong"),
  ])("欠損・不正な資格情報を拒否する: %s", (authorization) => {
    expect(hasValidBetaAccess(authorization, expected)).toBe(false);
  });
});
