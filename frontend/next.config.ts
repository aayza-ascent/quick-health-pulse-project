import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Pin the workspace root to this directory. Without it, Next walks up looking
  // for a lockfile and can settle on an unrelated one elsewhere on the machine,
  // which changes what gets traced into the build.
  outputFileTracingRoot: import.meta.dirname,
};

export default nextConfig;
