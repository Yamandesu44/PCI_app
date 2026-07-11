import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AppHeader } from "@/components/AppHeader";

import "./globals.css";

export const metadata: Metadata = {
  title: "PCI App — 競馬展開予想",
  description: "PCI を理解していなくても、レースの展開と恩恵を受ける馬がわかる。",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ja">
      <body>
        <AppHeader />
        {children}
      </body>
    </html>
  );
}
