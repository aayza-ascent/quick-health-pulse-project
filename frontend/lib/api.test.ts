import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fetchPulse } from "./api";
import type { Pulse } from "./types";

const VALID_PULSE: Pulse = {
  patient: {
    name: "Demo Patient",
    provider: "fitbit",
    provider_label: "Fitbit",
    is_connected: false,
    connection_status: "Demo data",
  },
  source: { provider: "fitbit", mode: "fixture", label: "Simulated Fitbit data", is_live: false },
  window: {
    anchor_date: "2026-09-08",
    baseline_days: 21,
    recent_days: 7,
    baseline_start: "2026-08-12",
    baseline_end: "2026-09-01",
    recent_start: "2026-09-02",
    recent_end: "2026-09-08",
  },
  headline: { title: "Potential change worth reviewing", body: "Sleep has decreased 18%.", metric: "sleep" },
  metrics: [],
  trends: [],
  generated_at: "2026-09-08T16:42:00Z",
  disclaimer: "This prototype is for demonstration purposes and is not a medical diagnostic tool.",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function mockFetch(impl: () => Promise<Response>) {
  vi.mocked(globalThis.fetch).mockImplementation(impl);
}

describe("fetchPulse", () => {
  it("returns the payload when the API responds normally", async () => {
    mockFetch(async () => jsonResponse(VALID_PULSE));

    const result = await fetchPulse();

    expect(result.ok).toBe(true);
    if (result.ok) expect(result.pulse.patient.name).toBe("Demo Patient");
  });

  it("never caches, because a stale pulse is worse than a slow one", async () => {
    mockFetch(async () => jsonResponse(VALID_PULSE));

    await fetchPulse();

    const [, init] = vi.mocked(globalThis.fetch).mock.calls[0] as [string, RequestInit];
    expect(init.cache).toBe("no-store");
  });

  it("passes through the backend error code so the UI can branch on it", async () => {
    mockFetch(async () =>
      jsonResponse(
        { error: { code: "junction_rate_limited", message: "Junction is rate-limiting." } },
        503,
      ),
    );

    const result = await fetchPulse();

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.code).toBe("junction_rate_limited");
  });

  it("reports an unreachable backend distinctly from a backend error", async () => {
    mockFetch(async () => {
      throw new TypeError("fetch failed");
    });

    const result = await fetchPulse();

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.code).toBe("backend_unreachable");
  });

  it("reports a timeout as unreachable and says so", async () => {
    mockFetch(async () => {
      const error = new Error("timed out");
      error.name = "TimeoutError";
      throw error;
    });

    const result = await fetchPulse();

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.code).toBe("backend_unreachable");
      expect(result.error.message).toContain("timed out");
    }
  });

  it("rejects a payload missing the fields the page renders", async () => {
    mockFetch(async () => jsonResponse({ patient: { name: "Demo" } }));

    const result = await fetchPulse();

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.code).toBe("malformed_response");
  });

  it("rejects a body that is not JSON at all", async () => {
    mockFetch(async () => new Response("<html>502 Bad Gateway</html>", { status: 200 }));

    const result = await fetchPulse();

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.code).toBe("malformed_response");
  });

  it("falls back to a generic code when an error body has no envelope", async () => {
    mockFetch(async () => jsonResponse({ detail: "Internal Server Error" }, 500));

    const result = await fetchPulse();

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.code).toBe("internal_error");
      expect(result.error.message).toContain("500");
    }
  });
});
