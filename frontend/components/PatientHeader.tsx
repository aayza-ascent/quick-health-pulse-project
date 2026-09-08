import type { DataSource, Patient } from "@/lib/types";

/**
 * Patient identity and provider attribution.
 *
 * The connection status is taken from the API rather than hard-coded, so
 * generated data is never presented as a live device connection.
 */
export function PatientHeader({ patient, source }: { patient: Patient; source: DataSource }) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <p className="eyebrow">Health Pulse</p>
        <h1 className="mt-1.5 text-2xl font-semibold tracking-tight text-ink sm:text-3xl">
          {patient.name}
        </h1>
        <p className="mt-1 flex items-center gap-2 text-sm text-ink-muted">
          <span>{patient.provider_label}</span>
          <span aria-hidden="true" className="text-ink-subtle">
            ·
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className={`size-1.5 rounded-full ${
                patient.is_connected ? "bg-ink-muted" : "bg-ink-subtle"
              }`}
            />
            {patient.connection_status}
          </span>
        </p>
      </div>

      {!source.is_live && (
        <p className="max-w-xs rounded-md border border-border-subtle bg-surface-muted px-3 py-2 text-xs leading-relaxed text-ink-muted">
          Running on generated data. Add a Junction sandbox key to read from the API.
        </p>
      )}
    </header>
  );
}
