import { type NextRequest, NextResponse } from "next/server";

import { hasValidBetaAccess } from "@/lib/betaAccess";

export function middleware(request: NextRequest) {
  const username = process.env.BETA_ACCESS_USER?.trim();
  const password = process.env.BETA_ACCESS_PASSWORD;

  if (!username && !password) return NextResponse.next();
  if (!username || !password) {
    return new NextResponse("ロケテスト認証の設定が完了していません。", {
      status: 503,
      headers: { "Cache-Control": "no-store" },
    });
  }

  if (
    hasValidBetaAccess(request.headers.get("Authorization"), {
      username,
      password,
    })
  ) {
    return NextResponse.next();
  }

  return new NextResponse("この画面は招待されたロケテスト参加者のみ利用できます。", {
    status: 401,
    headers: {
      "Cache-Control": "no-store",
      "WWW-Authenticate": 'Basic realm="PACE LAB beta", charset="UTF-8"',
    },
  });
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
