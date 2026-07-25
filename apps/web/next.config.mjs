/** @type {import('next').NextConfig} */
const nextConfig = {
  // 開発サーバーとロケテスト本番サーバーを同時起動できるよう、必要時だけ出力先を分離する。
  distDir: process.env.NEXT_DIST_DIR || ".next",
  // api-client は TypeScript ソースで配布するため Next 側でトランスパイルする。
  transpilePackages: ["@pci/api-client"],
  // Lint は CI（ruff/tsc/vitest）に委ね、build では実行しない。
  eslint: { ignoreDuringBuilds: true },
};

export default nextConfig;
