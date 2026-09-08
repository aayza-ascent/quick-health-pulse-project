import { Suspense } from "react";

import { ChangeCard } from "@/components/ChangeCard";
import { HealthChart } from "@/components/HealthChart";
import { MetricCard } from "@/components/MetricCard";
import { PatientHeader } from "@/components/PatientHeader";
import { SourceFooter } from "@/components/SourceFooter";
import { ErrorState, LoadingState } from "@/components/StateViews";
import { fetchPulse } from "@/lib/api";

/**
 * The dashboard.
 *
 * A server component, so the API call happens on the server and the browser
 * never holds a URL that could reach Junction. Rendered under Suspense with a
 * skeleton that matches the real layout.
 */
export default function Page() {
  return (
    <main className="mx-auto w-full max-w-3xl px-5 py-10 sm:px-6 sm:py-14">
      <Suspense fallback={<LoadingState />}>
        <Pulse />
      </Suspense>
    </main>
  );
}

async function Pulse() {
  const result = await fetchPulse();

  if (!result.ok) return <ErrorState error={result.error} />;

  const { pulse } = result;
  const headlineChange =
    pulse.metrics.find((metric) => metric.key === pulse.headline.metric) ?? null;

  // Sleep is the priority metric, so it gets the chart. Falling back to the
  // first available trend keeps the page intact if that ever changes.
  const chartTrend = pulse.trends.find((trend) => trend.key === "sleep") ?? pulse.trends[0];
  const chartChange = pulse.metrics.find((metric) => metric.key === chartTrend?.key);

  return (
    <div className="space-y-8">
      <PatientHeader patient={pulse.patient} source={pulse.source} />

      <section className="space-y-3">
        <h2 className="eyebrow">What changed?</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          {pulse.metrics.map((metric) => (
            <MetricCard key={metric.key} change={metric} />
          ))}
        </div>
      </section>

      <ChangeCard headline={pulse.headline} change={headlineChange} source={pulse.source} />

      {chartTrend && chartChange && <HealthChart trend={chartTrend} change={chartChange} />}

      <SourceFooter pulse={pulse} source={pulse.source} />
    </div>
  );
}
