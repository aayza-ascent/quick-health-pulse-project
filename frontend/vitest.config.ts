import { defineConfig } from "vitest/config";

export default defineConfig({
  // These are pure Node unit tests over lib/, with no component rendering and
  // no stylesheets. Supplying an inline PostCSS config stops Vite discovering
  // postcss.config.mjs, whose Tailwind v4 string-form plugin only Next resolves.
  css: { postcss: { plugins: [] } },
  test: {
    environment: "node",
    include: ["lib/**/*.test.ts"],
  },
});
