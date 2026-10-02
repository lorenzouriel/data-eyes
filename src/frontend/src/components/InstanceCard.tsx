import type { InstanceHealth, Severity } from "../types";
import { statusColorVar } from "../strata";
import WaitSparkline from "./WaitSparkline";

function fmtBytesPerSec(v?: number): string {
  if (v === undefined || v === null) return "—";
  if (v < 1024) return `${Math.round(v)} B/s`;
  if (v < 1024 * 1024) return `${(v / 1024).toFixed(1)} KB/s`;
  return `${(v / 1024 / 1024).toFixed(1)} MB/s`;
}

function fmtGB(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `${v.toFixed(1)} GB`;
}

function fmtKB(kb: number | null | undefined): string {
  if (kb === null || kb === undefined) return "—";
  if (kb < 1024 * 1024) return `${Math.round(kb / 1024)} MiB`;
  return `${(kb / 1024 / 1024).toFixed(1)} GiB`;
}

function fmtCompact(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(n);
}

function HealthDot({ label, severity }: { label: string; severity?: Severity }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <span className="status-dot" style={{ background: severity ? statusColorVar(severity) : "var(--line2)" }} />
      <span className="mono" style={{ fontSize: 10.5, letterSpacing: "0.04em", color: "var(--mid)" }}>{label}</span>
    </div>
  );
}

function SectionLabel({ children }: { children: string }) {
  return <span className="th-label">{children}</span>;
}

// Fleet "Cards" view — one instance's operational summary, modeled on
// references/dpa/database-in-cards.png but built from our own design tokens
// (statusColorVar/panel-card/th-label) instead of that reference's dark
// neon-green look, per "using our UI".
export default function InstanceCard({ instance, onSelect }: { instance: InstanceHealth; onSelect: (name: string) => void }) {
  const server = instance.server;
  const cpu = instance.cpu;
  const workers = instance.workers;
  const memory = instance.memory;
  const disk = instance.disk;

  const sqlPct = cpu?.sql_pct ?? null;
  const osTotalPct = cpu?.os_pct ?? null;
  const otherPct = sqlPct !== null && osTotalPct !== null ? Math.max(osTotalPct - sqlPct, 0) : null;
  const cpuPoints = (cpu?.history ?? []).filter((p) => p.CpuPct !== null && p.CpuPct !== undefined);
  const cpuMax = Math.max(...cpuPoints.map((p) => p.CpuPct), 1);

  const drives = Object.entries(disk ?? {}).sort(([a], [b]) => a.localeCompare(b));

  return (
    <div
      onClick={() => onSelect(instance.name)}
      className="panel-card"
      style={{
        borderLeft: `3px solid ${statusColorVar(instance.overall_severity)}`,
        padding: "15px 17px",
        display: "flex",
        flexDirection: "column",
        gap: 13,
        cursor: "pointer",
      }}
    >
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
          <span style={{ flex: 1, font: "600 14px 'Space Grotesk', sans-serif", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {instance.label}
          </span>
          <span className="status-dot" style={{ width: 9, height: 9, background: statusColorVar(instance.overall_severity) }} />
        </div>
        <span className="mono" style={{ fontSize: 10.5, color: "var(--muted)" }}>
          {server?.Cores ?? "—"} vCPU · {server?.TotalMemoryGB ?? "—"} GB
          {server?.Edition ? ` · ${server.Edition}` : ""}
        </span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <SectionLabel>CPU</SectionLabel>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ font: "600 25px 'Space Grotesk', sans-serif", letterSpacing: "-.8px", color: "var(--status-ok)" }}>
            {osTotalPct !== null ? Math.round(osTotalPct) : "—"}
            <span className="mono" style={{ fontSize: 12, color: "var(--muted)" }}>%</span>
          </span>
          <div style={{ flex: 1, display: "flex", alignItems: "flex-end", gap: 2, height: 30, minWidth: 0 }}>
            {cpuPoints.map((p, i) => (
              <div
                key={i}
                style={{
                  flex: 1,
                  height: `${Math.max(6, (p.CpuPct / cpuMax) * 100)}%`,
                  background: "var(--status-ok)",
                  opacity: 0.35 + 0.65 * (p.CpuPct / cpuMax),
                  borderRadius: 1.5,
                }}
              />
            ))}
          </div>
        </div>
        <span className="mono" style={{ fontSize: 10.5, color: "var(--muted)" }}>
          SQL {sqlPct !== null ? `${Math.round(sqlPct)}%` : "—"} · OS {otherPct !== null ? `${Math.round(otherPct)}%` : "—"}
        </span>
      </div>

      <div style={{ display: "flex", gap: 16, paddingTop: 2, paddingBottom: 2, borderTop: "1px solid var(--line2)", borderBottom: "1px solid var(--line2)" }}>
        <div style={{ padding: "8px 0" }}><HealthDot label="BLOCKING" severity={instance.categories.blocking} /></div>
        <div style={{ padding: "8px 0" }}><HealthDot label="JOBS" severity={instance.categories.job_health} /></div>
        <div style={{ padding: "8px 0" }}><HealthDot label="ERRORS" severity={instance.categories.errors} /></div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
        <SectionLabel>WORKERS</SectionLabel>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <span style={{ fontSize: 11, color: "var(--mid)" }}>Max / Created / Idle</span>
          <span className="mono" style={{ fontSize: 12 }}>
            {workers?.MaxWorkers ?? "—"} · {workers?.CreatedWorkers ?? "—"} · {workers?.IdleWorkers ?? "—"}
          </span>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
        <SectionLabel>MEMORY</SectionLabel>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <span style={{ fontSize: 11, color: "var(--mid)" }}>SQL / Target / Free</span>
          <span className="mono" style={{ fontSize: 12 }}>
            {fmtKB(memory?.SqlMemoryKB)} · {fmtKB(memory?.TargetMemoryKB)} · {fmtKB(memory?.FreeMemoryKB)}
          </span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <span style={{ fontSize: 11, color: "var(--mid)" }}>Page faults</span>
          <span className="mono" style={{ fontSize: 12 }}>{fmtCompact(memory?.PageFaults)}</span>
        </div>
      </div>

      {drives.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <SectionLabel>DISK &amp; IO</SectionLabel>
            <span className="mono" style={{ fontSize: 9.5, color: "var(--muted)" }}>FREE · IO · LATENCY</span>
          </div>
          {drives.map(([drive, d]) => (
            <div key={drive} style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <span className="mono" style={{ fontSize: 11.5 }}>{drive}</span>
              <span className="mono" style={{ fontSize: 11.5 }}>
                {fmtGB(d.free_gb)} · {fmtBytesPerSec(d.io_bytes_per_sec)} ·{" "}
                <span style={{ color: (d.latency_ms ?? 0) > 20 ? "var(--status-crit)" : "inherit" }}>
                  {d.latency_ms !== undefined ? `${Math.round(d.latency_ms)} ms` : "—"}
                </span>
              </span>
            </div>
          ))}
        </div>
      )}

      <WaitSparkline instanceName={instance.name} height={26} />
    </div>
  );
}
