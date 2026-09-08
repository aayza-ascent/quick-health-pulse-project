/**
 * The API contract, mirroring `backend/app/api/schemas.py`.
 *
 * Hand-written rather than generated: the surface is small, and writing it out
 * makes a backend change that breaks the contract show up as a type error here
 * instead of as `undefined` in the browser.
 */

export type MetricKey = "sleep" | "resting_heart_rate" | "activity";

export type MetricUnit = "seconds" | "bpm" | "steps";

export type ChangeDirection = "increased" | "decreased" | "stable" | "insufficient_data";

export type InsufficientReason =
  | "no_recent_data"
  | "no_baseline_data"
  | "low_recent_coverage"
  | "low_baseline_coverage"
  | "zero_baseline";

export interface Coverage {
  observed_days: number;
  expected_days: number;
  ratio: number;
}

export interface ComparisonWindow {
  label: string;
  start_date: string;
  end_date: string;
  /** Mean over observed days only. Null when nothing was measured. */
  mean: number | null;
  coverage: Coverage;
}

/** Which upstream Junction field produced a metric, and on how many days. */
export interface Derivation {
  field: string;
  days: number;
}

export interface MetricChange {
  key: MetricKey;
  label: string;
  unit: MetricUnit;
  description: string;
  direction: ChangeDirection;
  verdict: string;
  summary: string;
  latest_value: number | null;
  latest_day: string | null;
  pct_change: number | null;
  absolute_change: number | null;
  threshold_pct: number;
  insufficient_reason: InsufficientReason | null;
  baseline: ComparisonWindow;
  recent: ComparisonWindow;
  derivations: Derivation[];
}

/** One day on a chart. A null value is a day the provider recorded nothing. */
export interface TrendPoint {
  day: string;
  value: number | null;
}

export interface Trend {
  key: MetricKey;
  label: string;
  unit: MetricUnit;
  points: TrendPoint[];
  coverage: Coverage;
}

export interface Patient {
  name: string;
  provider: string;
  provider_label: string;
  is_connected: boolean;
  connection_status: string;
}

export interface DataSource {
  provider: string;
  mode: "junction" | "fixture";
  /** Attribution shown verbatim, e.g. "Fitbit via Junction". */
  label: string;
  is_live: boolean;
}

export interface WindowSpec {
  /** Last day with data. The window ends here, not today. */
  anchor_date: string;
  baseline_days: number;
  recent_days: number;
  baseline_start: string;
  baseline_end: string;
  recent_start: string;
  recent_end: string;
}

export interface Headline {
  title: string;
  body: string;
  metric: MetricKey | null;
}

export interface Pulse {
  patient: Patient;
  source: DataSource;
  window: WindowSpec;
  headline: Headline;
  metrics: MetricChange[];
  trends: Trend[];
  generated_at: string;
  disclaimer: string;
}

/**
 * Error codes the backend can return, plus two the client raises itself when it
 * cannot reach or cannot read the backend. The UI branches on these rather than
 * on message text.
 */
export type ApiErrorCode =
  | "not_configured"
  | "junction_error"
  | "junction_unauthorised"
  | "junction_not_found"
  | "junction_rate_limited"
  | "junction_unavailable"
  | "internal_error"
  | "backend_unreachable"
  | "malformed_response";

export interface ApiError {
  code: ApiErrorCode;
  message: string;
}

export type PulseResult = { ok: true; pulse: Pulse } | { ok: false; error: ApiError };
