"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useChartColors } from "@/lib/chartTheme";
import { formatDayShort, formatValue } from "@/lib/format";
import type { MetricChange, Trend } from "@/lib/types";

/**
 * A metric's recent history.
 *
 * Two choices matter here:
 *
 * `connectNulls` is false, so a day with no measurement leaves a visible break
 * in the line. Bridging the gap would draw a line through data that does not
 * exist, which is the charting equivalent of zero-filling.
 *
 * The recent window is shaded and the baseline mean drawn as a reference line,
 * so the comparison the insight is based on is visible in the chart rather than
 * only stated in prose.
 *
 * Colours come from useChartColors rather than from `var(--token)` directly;
 * see lib/chartTheme.ts for why that distinction matters here.
 */
export function HealthChart({ trend, change }: { trend: Trend; change: MetricChange }) {
  const colors = useChartColors();
  const data = trend.points.map((point) => ({ day: point.day, value: point.value }));
  const gaps = trend.points.filter((point) => point.value === null).length;

  return (
    <section className="rounded-lg border border-border-subtle bg-surface p-4 sm:p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-medium text-ink">
          {trend.label} <span className="text-ink-subtle">· last {trend.points.length} days</span>
        </h2>
        {gaps > 0 && (
          <p className="tabular text-xs text-ink-subtle">
            {gaps} {gaps === 1 ? "day" : "days"} without data
          </p>
        )}
      </div>

      <div className="mt-4 h-52 w-full sm:h-60">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={colors.grid} vertical={false} />

            {/* The window the insight compares against. */}
            <ReferenceArea
              x1={change.recent.start_date}
              x2={change.recent.end_date}
              fill={colors.baseline}
              fillOpacity={0.12}
              strokeOpacity={0}
            />

            {change.baseline.mean !== null && (
              <ReferenceLine
                y={change.baseline.mean}
                stroke={colors.baseline}
                strokeDasharray="3 3"
              />
            )}

            <XAxis
              dataKey="day"
              tickFormatter={formatDayShort}
              tick={{ fill: colors.axisText, fontSize: 11 }}
              stroke={colors.axis}
              interval="preserveStartEnd"
              minTickGap={40}
            />
            <YAxis
              tick={{ fill: colors.axisText, fontSize: 11 }}
              stroke={colors.axis}
              tickFormatter={(value: number) => formatValue(value, trend.unit)}
              width={64}
              domain={yDomain(trend)}
            />

            <Tooltip
              content={({ active, payload, label }) => {
                if (!active || typeof label !== "string") return null;
                const value = payload?.[0]?.value;
                return (
                  <div className="rounded-md border border-border-strong bg-surface px-3 py-2 text-xs shadow-sm">
                    <p className="font-medium text-ink">{formatDayShort(label)}</p>
                    <p className="tabular mt-0.5 text-ink-muted">
                      {typeof value === "number"
                        ? formatValue(value, trend.unit)
                        : "No data available for this day."}
                    </p>
                  </div>
                );
              }}
            />

            <Line
              type="monotone"
              dataKey="value"
              stroke={colors.line}
              strokeWidth={2}
              // Observed days are marked individually, not just joined into a
              // line. With sparse real data a measurement can have no observed
              // neighbour to draw a segment to, and a dot-less line renders
              // those days as nothing at all — an empty chart for a patient who
              // does have data.
              dot={{ r: 1.8, fill: colors.line, strokeWidth: 0 }}
              activeDot={{ r: 3.5, fill: colors.line }}
              // Never bridge a missing day: a gap in the data is a gap in the
              // line. Bridging it would draw through measurements that do not
              // exist, which is the charting equivalent of zero-filling.
              connectNulls={false}
              // Colours resolve after mount, which re-renders this chart. With
              // the entry animation on, that restarts it and the line flickers
              // through an empty frame. A dashboard gains nothing from the
              // animation, so it goes.
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <p className="mt-3 text-xs leading-relaxed text-ink-subtle">
        Shaded band: the recent {change.recent.coverage.expected_days}-day window. Dashed line: the{" "}
        {change.baseline.coverage.expected_days}-day baseline average. Breaks in the line are days
        with no recorded measurement.
      </p>
    </section>
  );
}

/**
 * Y bounds with a little headroom, computed here rather than handed to Recharts
 * as a "dataMin - x" string: those strings only accept a plain number, so an
 * expression like "dataMin - dataMin * 0.15" silently fails to parse.
 *
 * Starting the axis a margin below the lowest reading rather than at zero keeps
 * a change of a few percent legible, which is the whole point of the chart.
 */
function yDomain(trend: Trend): [number, number] {
  const values = trend.points
    .map((point) => point.value)
    .filter((value): value is number => value !== null);

  if (values.length === 0) return [0, 1];

  const min = Math.min(...values);
  const max = Math.max(...values);
  const padding = Math.max((max - min) * 0.35, max * 0.04);

  return [Math.max(0, min - padding), max + padding * 0.4];
}
