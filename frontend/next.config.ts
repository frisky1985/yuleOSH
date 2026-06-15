import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
  assetPrefix: ".",
  trailingSlash: true,
};

export default nextConfig;
