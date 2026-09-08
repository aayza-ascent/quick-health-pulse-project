import type { ApiError, ApiErrorCode } from "@/lib/types";

/**
 * What the page shows when it has nothing to show.
 *
 * Each failure gets its own next step. A dashboard that says only "something
 * went wrong" leaves the reader unable to tell an unconfigured key from a
 * provider outage, when the fix is completely different.
 */
const NEXT_STEPS: Record<ApiErrorCode, string> = {
  not_configured:
    "Add a Junction sandbox key to backend/.env, or set HEALTH_PULSE_DATA_SOURCE=fixture to explore the app with generated data.",
  junction_unauthorised: "Junction rejected the API key. Check JUNCTION_API_KEY in backend/.env.",
  junction_not_found:
    "Junction has no record of this user. Demo users expire after 7 days — create a new one with POST /api/demo/provision.",
  junction_rate_limited: "Junction is rate-limiting requests. Wait a moment and reload.",
  junction_unavailable: "Junction could not be reached. This is usually temporary.",
  junction_error: "Junction returned a response the service could not use.",
  backend_unreachable: "Start the API with `uvicorn app.main:app --reload` in the backend folder.",
  malformed_response:
    "The API contract and this page have diverged. Check that both are running the same revision.",
  internal_error: "Check the backend logs for the full traceback.",
};

export function ErrorState({ error }: { error: ApiError }) {
  return (
    <div className="rounded-lg border border-border-subtle bg-surface p-6">
      <p className="eyebrow">Could not load this pulse</p>
      <p className="mt-2 max-w-prose text-[0.9375rem] leading-relaxed text-ink">{error.message}</p>
      <p className="mt-3 max-w-prose text-sm leading-relaxed text-ink-muted">
        {NEXT_STEPS[error.code]}
      </p>
      <p className="tabular mt-4 text-xs text-ink-subtle">Error code: {error.code}</p>
    </div>
  );
}

/**
 * Shown while the server component resolves.
 *
 * Mirrors the real layout rather than showing a spinner, so the page does not
 * reflow once the data lands.
 */
export function LoadingState() {
  return (
    <div aria-busy="true" aria-live="polite" className="space-y-6">
      <span className="sr-only">Loading health data</span>

      <div className="space-y-2">
        <Placeholder className="h-3 w-24" />
        <Placeholder className="h-8 w-48" />
        <Placeholder className="h-3 w-32" />
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        {[0, 1, 2].map((index) => (
          <div
            key={index}
            className="space-y-3 rounded-lg border border-border-subtle bg-surface p-5"
          >
            <Placeholder className="h-3 w-20" />
            <Placeholder className="h-7 w-24" />
            <Placeholder className="h-3 w-28" />
          </div>
        ))}
      </div>

      <Placeholder className="h-28 w-full rounded-lg" />
      <Placeholder className="h-64 w-full rounded-lg" />
    </div>
  );
}

function Placeholder({ className }: { className: string }) {
  return <div className={`animate-pulse rounded bg-surface-muted ${className}`} />;
}
