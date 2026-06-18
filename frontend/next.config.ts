import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
  assetPrefix: "/yuleOSH",
  trailingSlash: true,
  turbopack: {
    root: "/Users/stefan/.openclaw/workspace/tasks/yuleOSH/frontend",
  },
};

export default nextConfig;
