import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  // Keep production builds separate from a live development preview, which
  // otherwise holds the default .next cache open on Windows.
  distDir: ".next-build",
  images: { unoptimized: true },
};

export default nextConfig;
