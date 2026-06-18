/** @type {import('next').NextConfig} */
const nextConfig = {
  // api-client は TypeScript ソースで配布するため Next 側でトランスパイルする。
  transpilePackages: ["@pci/api-client"],
  // Lint は CI（ruff/tsc/vitest）に委ね、build では実行しない。
  eslint: { ignoreDuringBuilds: true },
};

export default nextConfig;
