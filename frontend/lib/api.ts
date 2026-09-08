/**
 * Server-side client for the Health Pulse API.
 *
 * Every call runs on the Next.js server, never in the browser. That is the
 * whole point of having a backend in front of Junction: the API key stays on
 * the server, and the browser only ever sees derived numbers.
 */

import type { ApiError, Pulse, PulseResult } from "./types";

const DEFAULT_API_URL = "http://localhost:8000";
const REQUEST_TIMEOUT_MS = 12_000;

function apiUrl(path: string): string {
  const base = process.env.HEALTH_PULSE_API_URL ?? DEFAULT_API_URL;
  return `${base.replace(/\/$/, "")}${path}`;
}

function failure(code: ApiError["code"], message: string): PulseResult {
  return { ok: false, error: { code, message } };
}

/**
 * Narrow an unknown response body to a Pulse.
 *
 * Only the fields the page actually renders are checked. The aim is to fail
 * with a clear message when the backend contract has moved, rather than to
 * re-implement the schema — a half-rendered dashboard is worse than an honest
 * error.
 */
function isPulse(body: unknown): body is Pulse {
  if (typeof body !== "object" || body === null) return false;
  const candidate = body as Partial<Pulse>;
  return (
    Array.isArray(candidate.metrics) &&
    Array.isArray(candidate.trends) &&
    typeof candidate.disclaimer === "string" &&
    typeof candidate.generated_at === "string" &&
    typeof candidate.patient === "object" &&
    candidate.patient !== null &&
    typeof candidate.source === "object" &&
    candidate.source !== null &&
    typeof candidate.window === "object" &&
    candidate.window !== null &&
    typeof candidate.headline === "object" &&
    candidate.headline !== null
  );
}

function parseErrorBody(body: unknown, status: number): PulseResult {
  if (typeof body === "object" && body !== null && "error" in body) {
    const envelope = (body as { error?: Partial<ApiError> }).error;
    if (envelope?.code && envelope.message) {
      return { ok: false, error: { code: envelope.code, message: envelope.message } };
    }
  }
  return failure("internal_error", `The API responded with status ${status}.`);
}

/**
 * Fetch the full dashboard payload.
 *
 * Returns a result object rather than throwing, so the page renders a specific
 * explanation for each failure instead of a generic error boundary. Which
 * failure occurred is genuinely useful here: an unconfigured key, an
 * unreachable backend and a rate-limited provider need different next steps.
 */
export async function fetchPulse(): Promise<PulseResult> {
  let response: Response;

  try {
    response = await fetch(apiUrl("/api/pulse"), {
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      // Health data changes through the day and the payload is small, so there
      // is nothing to gain from caching a stale pulse.
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
  } catch (error) {
    const reason = error instanceof Error && error.name === "TimeoutError" ? "timed out" : "failed";
    return failure(
      "backend_unreachable",
      `The request to the Health Pulse API ${reason}. Is the backend running on ${apiUrl("")}?`,
    );
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return failure("malformed_response", "The API returned a response that was not valid JSON.");
  }

  if (!response.ok) return parseErrorBody(body, response.status);

  if (!isPulse(body)) {
    return failure("malformed_response", "The API returned a payload this page could not read.");
  }

  return { ok: true, pulse: body };
}
