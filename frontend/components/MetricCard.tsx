import { directionArrow, formatPercent, formatValue, isFullyCovered } from "@/lib/format";
import type { MetricChange } from "@/lib/types";

/**
 * One metric: its recent average and how that compares with its baseline.
 *
 * The headline figure is the recent-window average, not the latest single
 * reading. The percentage beside it compares two averages, so showing one
 * night's value next to it would put two different things on the same line and
 * invite the reader to relate them. The most recent day is reported in the
 * footer instead, where it is labelled as such.
 *
 * Direction is carried by the arrow alone and the percentage is unsigned: "↓
 * 18%" rather than "↓ −18%". Neither is coloured — see app/globals.css for why.
 */
export function MetricCard({ change }: { change: MetricChange }) {
  const insufficient = change.direction === "insufficient_data";
  const recent = change.recent;

  return (
    <div className="flex flex-col rounded-lg border border-border-subtle bg-surface p-4 sm:p-5">
      <p className="text-sm font-medium text-ink-muted">{change.label}</p>

      <p className="tabular mt-2 text-2xl font-semibold tracking-tight text-ink sm:text-[1.75rem]">
        {insufficient ? "—" : formatValue(recent.mean, change.unit)}
      </p>

      {!insufficient && (
        <p className="tabular mt-1 text-xs text-ink-subtle">
          {recent.coverage.expected_days}-day average
        </p>
      )}

      <p className="tabular mt-3 flex items-baseline gap-1.5 text-sm text-ink-muted">
        <span aria-hidden="true" className="text-ink-subtle">
          {directionArrow(change.direction)}
        </span>
        {insufficient ? (
          <span>Not enough data</span>
        ) : change.direction === "stable" ? (
          <span>Stable vs baseline</span>
        ) : (
          <span>
            {formatPercent(change.pct_change)} <span className="text-ink-subtle">vs baseline</span>
          </span>
        )}
      </p>

      {/* Coverage is shown on the card, not only in the evidence view: a mean
          over 4 of 7 days should carry a visible caveat wherever it appears. */}
      {!isFullyCovered(recent.coverage) && !insufficient && (
        <p className="tabular mt-2 text-xs text-ink-subtle">
          {recent.coverage.observed_days} of {recent.coverage.expected_days} days recorded
        </p>
      )}
    </div>
  );
}
