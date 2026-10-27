import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
  assetPrefix: "/yuleOSH",
  trailingSlash: true,
  // Dev-only proxy: when running `npm run dev`, the desktop page at /desktop
  // uses relative /api/* paths. Without this they hit the Next.js dev server
  // (:3000) instead of the Python backend (:18788). In production the Electron
  // static file server already proxies /api/*, so this rewrite is only
  // active during development (rewrites are ignored for static export builds).
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:18788/api/:path*",
      },
    ];
  },
};

export default nextConfig;
