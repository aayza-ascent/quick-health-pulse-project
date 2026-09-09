import path from "node:path";
import { fileURLToPath } from "node:url";

import type { NextConfig } from "next";

// Resolved via import.meta.url rather than import.meta.dirname: the latter only
// exists from Node 20.11, and on anything older it is silently undefined, which
// would leave outputFileTracingRoot unset without any error to explain why.
// This form works on every Node version Next itself supports.
const projectRoot = path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Pin the workspace root to this directory. Without it, Next walks up looking
  // for a lockfile and can settle on an unrelated one elsewhere on the machine,
  // which changes what gets traced into the build.
  outputFileTracingRoot: projectRoot,
};

export default nextConfig;
