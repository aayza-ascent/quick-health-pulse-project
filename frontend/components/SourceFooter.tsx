import { formatClockTime, formatDayLong } from "@/lib/format";
import type { DataSource, Pulse } from "@/lib/types";

/**
 * Provenance and the disclaimer.
 *
 * "Last updated" reports when this pulse was computed, and is shown next to the
 * last day that actually has data. Those are different facts, and conflating
 * them would let a freshly computed page imply fresh measurements.
 */
export function SourceFooter({ pulse, source }: { pulse: Pulse; source: DataSource }) {
  return (
    <footer className="space-y-4 border-t border-border-subtle pt-5">
      <dl className="grid gap-4 text-xs sm:grid-cols-3">
        <div>
          <dt className="text-ink-subtle">Source</dt>
          <dd className="mt-0.5 text-ink-muted">{source.label}</dd>
        </div>
        <div>
          <dt className="text-ink-subtle">Most recent data</dt>
          <dd className="tabular mt-0.5 text-ink-muted">{formatDayLong(pulse.window.anchor_date)}</dd>
        </div>
        <div>
          <dt className="text-ink-subtle">Last updated</dt>
          <dd className="tabular mt-0.5 text-ink-muted">{formatClockTime(pulse.generated_at)}</dd>
        </div>
      </dl>

      <p className="max-w-prose text-xs leading-relaxed text-ink-subtle">{pulse.disclaimer}</p>
    </footer>
  );
}
