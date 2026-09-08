"use client";

import { useState } from "react";

import type { DataSource, Headline, MetricChange } from "@/lib/types";

import { Evidence } from "./Evidence";

/**
 * The single change worth reviewing, with its evidence one click away.
 *
 * Client component purely because the evidence panel toggles. The content is
 * rendered on the server and passed in, so the reasoning is not reconstructed
 * in the browser.
 */
export function ChangeCard({
  headline,
  change,
  source,
}: {
  headline: Headline;
  change: MetricChange | null;
  source: DataSource;
}) {
  const [showEvidence, setShowEvidence] = useState(false);

  // Nothing crossed the threshold. Still worth stating plainly: "no notable
  // changes" is a finding, and a blank space is not.
  if (!change) {
    return (
      <section className="rounded-lg border border-border-subtle bg-surface p-5">
        <p className="text-sm font-medium text-ink">{headline.title}</p>
        <p className="mt-1.5 text-sm leading-relaxed text-ink-muted">{headline.body}</p>
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-accent-border bg-accent-surface p-5">
      <p className="text-sm font-medium text-accent">{headline.title}</p>

      <p className="mt-1.5 max-w-prose text-[0.9375rem] leading-relaxed text-ink">
        {headline.body}
      </p>

      <button
        type="button"
        onClick={() => setShowEvidence((open) => !open)}
        aria-expanded={showEvidence}
        aria-controls="evidence-panel"
        className="mt-4 inline-flex items-center gap-1.5 rounded-md border border-border-strong bg-surface px-3 py-1.5 text-sm font-medium text-ink transition-colors hover:bg-surface-muted"
      >
        {showEvidence ? "Hide evidence" : "View evidence"}
        <span aria-hidden="true" className="text-ink-subtle">
          {showEvidence ? "↑" : "↓"}
        </span>
      </button>

      {showEvidence && (
        <div id="evidence-panel">
          <Evidence change={change} source={source} />
        </div>
      )}
    </section>
  );
}
