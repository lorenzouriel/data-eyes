import { useEffect, useState } from "react";
import { getAdvisorReport, dismissAdvisorFinding, ApiError } from "../../api";
import { statusColorVar, tagStyle } from "../../strata";
import type { AdvisorFinding, AdvisorReport, Severity } from "../../types";

function normalizeSeverity(raw: string): Severity {
  const upper = raw.toUpperCase();
  return upper === "CRITICAL" || upper === "WARNING" || upper === "OK" ? (upper as Severity) : "UNKNOWN";
}

function FindingCard({
  instanceName,
  finding,
  onDismiss,
}: {
  instanceName: string;
  finding: AdvisorFinding;
  onDismiss: () => void;
}) {
  const [dismissing, setDismissing] = useState(false);
  const color = statusColorVar(normalizeSeverity(finding.severity));

  return (
    <div className="panel-card" style={{ padding: 18, display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
          <span className="status-dot" style={{ background: color }} />
          <h3 style={{ margin: 0, font: "600 15px 'Space Grotesk', sans-serif" }}>{finding.title}</h3>
          <span className="tag" style={tagStyle(color)}>{finding.severity}</span>
        </div>
        <button
          className="btn-ghost"
          disabled={dismissing}
          onClick={async () => {
            setDismissing(true);
            try {
              await dismissAdvisorFinding(instanceName, finding.finding_key);
            } finally {
              onDismiss();
            }
          }}
        >
          Dismiss
        </button>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <span className="th-label">REASONING</span>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {finding.timeline.map((step, i) => (
            <div key={i} style={{ display: "flex", gap: 10, alignItems: "baseline" }}>
              <span className="mono" style={{ flex: "none", width: 78, fontSize: 10.5, color: "var(--muted)", textTransform: "uppercase" }}>
                {step.stage}
              </span>
              <span style={{ fontSize: 12.5, color: "var(--mid)" }}>{step.detail}</span>
            </div>
          ))}
        </div>
      </div>

      {finding.evidence.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span className="th-label">EVIDENCE</span>
          <ul style={{ margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 3 }}>
            {finding.evidence.map((e, i) => (
              <li key={i} style={{ fontSize: 12.5, color: "var(--mid)" }}>{e}</li>
            ))}
          </ul>
        </div>
      )}

      {finding.proposed_ddl && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span className="th-label">PROPOSED DDL — REVIEW BEFORE RUNNING, NOT APPLIED AUTOMATICALLY</span>
          <pre
            className="mono"
            style={{ margin: 0, padding: "12px 14px", fontSize: 11.5, lineHeight: 1.7, background: "var(--soft)", borderRadius: 8, overflowX: "auto" }}
          >
            {finding.proposed_ddl}
          </pre>
        </div>
      )}

      {finding.risks.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span className="th-label">RISKS</span>
          <ul style={{ margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 3 }}>
            {finding.risks.map((r, i) => (
              <li key={i} style={{ fontSize: 12.5, color: statusColorVar("WARNING") }}>{r}</li>
            ))}
          </ul>
        </div>
      )}

      {finding.estimated_impact && (
        <div style={{ fontSize: 11.5, color: "var(--muted)", borderTop: "1px solid var(--line2)", paddingTop: 10 }}>
          {finding.estimated_impact}
        </div>
      )}
    </div>
  );
}

export default function AdvisorTab({ instanceName }: { instanceName: string }) {
  const [report, setReport] = useState<AdvisorReport | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    setReport(undefined);
    setError(null);
    getAdvisorReport(instanceName)
      .then(setReport)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Advisor request failed."));
  }, [instanceName, refreshKey]);

  const dismiss = (findingKey: string) => {
    setReport((prev) => (prev ? { ...prev, findings: prev.findings.filter((f) => f.finding_key !== findingKey) } : prev));
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
        <p style={{ margin: 0, fontSize: 12.5, color: "var(--muted)" }}>
          Drafted by Claude from this instance's live wait, blocking, top-query, and missing-index data — reviewed
          suggestions, not applied or benchmarked changes.
        </p>
        <button className="btn-ghost" onClick={() => setRefreshKey((k) => k + 1)} disabled={report === undefined}>
          Regenerate
        </button>
      </div>

      {report === undefined && <div className="page-loading">Drafting advisor report…</div>}
      {error && <div className="banner-error">{error}</div>}
      {report && (
        <>
          <div className="panel-card" style={{ padding: 16, fontSize: 13, color: "var(--mid)" }}>{report.summary}</div>
          {report.findings.length === 0 ? (
            <div className="empty-state">No actionable findings right now.</div>
          ) : (
            report.findings.map((f) => (
              <FindingCard key={f.finding_key} instanceName={instanceName} finding={f} onDismiss={() => dismiss(f.finding_key)} />
            ))
          )}
        </>
      )}
    </div>
  );
}
