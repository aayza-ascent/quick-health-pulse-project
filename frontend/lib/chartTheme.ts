"use client";

import { useEffect, useState } from "react";

/**
 * Resolves the chart design tokens to concrete colour values.
 *
 * Recharts applies `stroke` and `fill` as SVG *presentation attributes*, and
 * `var(--token)` is not valid there — CSS custom properties only resolve in CSS
 * property values. Passing them straight through fails silently: the attribute
 * is ignored, the element falls back to a library default, and a line can end
 * up with no visible stroke at all.
 *
 * So the variables are read from the document at runtime and handed to Recharts
 * as plain strings. Reading them rather than duplicating the hex values keeps
 * app/globals.css the single source of truth for the palette, and re-reading on
 * a colour-scheme change keeps the chart in step with the rest of the page.
 */
const CHART_TOKENS = {
  line: "--chart-line",
  grid: "--chart-grid",
  baseline: "--chart-baseline",
  axis: "--border",
  axisText: "--text-subtle",
} as const;

export type ChartColors = Record<keyof typeof CHART_TOKENS, string>;

/** Used for the first render and on the server, before the document is readable. */
const FALLBACK: ChartColors = {
  line: "#44403c",
  grid: "#ececea",
  baseline: "#a8a29e",
  axis: "#e7e5e4",
  axisText: "#8a8279",
};

function readTokens(): ChartColors {
  const styles = getComputedStyle(document.documentElement);
  const entries = Object.entries(CHART_TOKENS).map(([name, token]) => {
    const value = styles.getPropertyValue(token).trim();
    return [name, value || FALLBACK[name as keyof ChartColors]];
  });
  return Object.fromEntries(entries) as ChartColors;
}

export function useChartColors(): ChartColors {
  const [colors, setColors] = useState<ChartColors>(FALLBACK);

  useEffect(() => {
    const sync = () => setColors(readTokens());
    sync();

    const media = window.matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);

  return colors;
}
