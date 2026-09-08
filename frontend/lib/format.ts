/**
 * Presentation helpers.
 *
 * The backend sends raw numbers with a unit; formatting happens here so the API
 * stays a data contract rather than a source of display strings.
 */

import type { ChangeDirection, MetricUnit } from "./types";

/** Seconds to "6h 18m". Rounds to the nearest minute; sub-minute precision is noise. */
export function formatDuration(seconds: number): string {
  const totalMinutes = Math.round(seconds / 60);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours === 0) return `${minutes}m`;
  return `${hours}h ${String(minutes).padStart(2, "0")}m`;
}

export function formatValue(value: number | null, unit: MetricUnit): string {
  if (value === null) return "—";
  switch (unit) {
    case "seconds":
      return formatDuration(value);
    case "bpm":
      return `${Math.round(value)} bpm`;
    case "steps":
      return Math.round(value).toLocaleString("en-GB");
  }
}

/** A signed percentage, rounded for display: -17.76 becomes "18%". */
export function formatPercent(pct: number | null): string {
  if (pct === null) return "—";
  return `${Math.abs(Math.round(pct))}%`;
}

export function formatSignedPercent(pct: number | null): string {
  if (pct === null) return "—";
  const rounded = Math.round(pct);
  const sign = rounded > 0 ? "+" : rounded < 0 ? "−" : "";
  return `${sign}${Math.abs(rounded)}%`;
}

/**
 * Arrow for a direction.
 *
 * Direction only, never a value judgement: less sleep is not annotated as bad,
 * and a lower resting heart rate is not annotated as good. That reading belongs
 * to a clinician, not to a percentage threshold.
 */
export function directionArrow(direction: ChangeDirection): string {
  switch (direction) {
    case "increased":
      return "↑";
    case "decreased":
      return "↓";
    case "stable":
      return "→";
    case "insufficient_data":
      return "·";
  }
}

/** ISO date to "12 Aug". */
export function formatDayShort(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}

/** ISO date to "12 Aug 2026". */
export function formatDayLong(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

/** ISO datetime to "16:42". */
export function formatClockTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

export function formatDateRange(start: string, end: string): string {
  return `${formatDayShort(start)} – ${formatDayShort(end)}`;
}

/** "19 of 21 days" — coverage in words, for the evidence view. */
export function formatCoverage(observed: number, expected: number): string {
  return `${observed} of ${expected} days`;
}

/** Whether every day in a window carried a measurement. */
export function isFullyCovered(coverage: { observed_days: number; expected_days: number }): boolean {
  return coverage.observed_days >= coverage.expected_days;
}
