import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AppHeader } from "@/components/AppHeader";
import { SiteFooter } from "@/components/SiteFooter";

import "./globals.css";

export const metadata: Metadata = {
  // 表に出す名前は PACE LAB に統一する（ヘッダー・Basic認証のレルムと揃える）。
  // 指標名（PCI）は利用者向けの文言に出さない。理解していなくても使えることが
  // この製品の value なので、名乗りに出てくるのは筋が通らない。
  title: "PACE LAB — 競馬展開予想",
  description: "難しい指標を知らなくても、レースの展開と、展開が向く馬がわかる。",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ja">
      <body>
        <AppHeader />
        {children}
        <SiteFooter />
      </body>
    </html>
  );
}
