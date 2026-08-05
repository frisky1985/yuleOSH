import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
  assetPrefix: "/yuleOSH",
  trailingSlash: true,
};

export default nextConfig;
