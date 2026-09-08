import {
  formatCoverage,
  formatDateRange,
  formatSignedPercent,
  formatValue,
  isFullyCovered,
} from "@/lib/format";
import type { DataSource, MetricChange } from "@/lib/types";

/**
 * Why an insight appeared.
 *
 * This is the point of the project. If the app states that sleep is down 18%,
 * the reader can open this panel and see the two averages, the arithmetic
 * between them, how many days each average is based on, and which Junction
 * field the numbers came from. Every figure here is computed alongside the
 * headline in the same request, so the explanation cannot disagree with the
 * claim it explains.
 */
export function Evidence({ change, source }: { change: MetricChange; source: DataSource }) {
  const rows = buildRows(change);

  return (
    <div className="mt-4 border-t border-border-subtle pt-4">
      <p className="eyebrow">Why this appeared</p>

      <dl className="mt-3 grid gap-x-8 gap-y-3 sm:grid-cols-2">
        {rows.map((row) => (
          <div key={row.term} className="min-w-0">
            <dt className="text-xs text-ink-subtle">{row.term}</dt>
            <dd className="tabular mt-0.5 text-sm text-ink">{row.value}</dd>
            {row.note && <p className="mt-0.5 text-xs text-ink-subtle">{row.note}</p>}
          </div>
        ))}

        <div className="min-w-0">
          <dt className="text-xs text-ink-subtle">Source</dt>
          <dd className="mt-0.5 text-sm text-ink">{source.label}</dd>
        </div>
      </dl>

      <p className="mt-4 text-xs leading-relaxed text-ink-subtle">
        Averages are taken over days with a recorded measurement. Days the device recorded nothing
        are excluded rather than counted as zero, which is why the coverage figures above are
        stated alongside each average.
      </p>
    </div>
  );
}

interface EvidenceRow {
  term: string;
  value: string;
  note?: string;
}

function buildRows(change: MetricChange): EvidenceRow[] {
  const { baseline, recent, unit } = change;

  const rows: EvidenceRow[] = [
    {
      term: baseline.label,
      value: formatValue(baseline.mean, unit),
      note: formatDateRange(baseline.start_date, baseline.end_date),
    },
    {
      term: recent.label,
      value: formatValue(recent.mean, unit),
      note: formatDateRange(recent.start_date, recent.end_date),
    },
  ];

  if (change.pct_change !== null) {
    rows.push({
      term: "Change",
      value: formatSignedPercent(change.pct_change),
      note: `Reported when the difference exceeds ${change.threshold_pct}%`,
    });
  }

  rows.push({
    term: "Data coverage",
    value: formatCoverage(recent.coverage.observed_days, recent.coverage.expected_days),
    note: isFullyCovered(recent.coverage)
      ? "Recent window fully recorded"
      : `Baseline: ${formatCoverage(
          baseline.coverage.observed_days,
          baseline.coverage.expected_days,
        )}`,
  });

  // Only worth showing when the metric was not read from a single field
  // throughout. When it was, naming that field adds noise rather than clarity.
  if (change.derivations.length > 1) {
    rows.push({
      term: "Measured from",
      value: change.derivations.map((d) => `${d.field} (${d.days}d)`).join(", "),
      note: "Provider coverage differs by day, so the closest available reading is used",
    });
  }

  return rows;
}
