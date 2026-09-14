import { useEffect, useState } from "react";
import { useInstanceTab } from "../../hooks/useInstanceTab";
import { getQueryPlan } from "../../api";
import { statusColorVar } from "../../strata";
import type { PlanNode, QueryPlan, TopQueryRow } from "../../types";

function PlanDetail({ instanceName, row, onBack }: { instanceName: string; row: TopQueryRow; onBack: () => void }) {
  const [plan, setPlan] = useState<QueryPlan | null | undefined>(undefined);

  useEffect(() => {
    setPlan(undefined);
    getQueryPlan(instanceName, row.PlanHandle)
      .then(setPlan)
      .catch(() => setPlan(null));
  }, [instanceName, row.PlanHandle]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", justifyContent: "space-between", gap: 12 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
          <a
            href="#"
            onClick={(e) => {
              e.preventDefault();
              onBack();
            }}
            style={{ fontSize: 11.5, color: "var(--muted)" }}
          >
            ← All statements
          </a>
          <h2 style={{ margin: 0, font: "600 18px 'Space Grotesk', sans-serif", letterSpacing: "-.4px" }}>
            {row.QueryText.length > 60 ? row.QueryText.slice(0, 60) + "…" : row.QueryText}
          </h2>
          <span className="mono" style={{ fontSize: 11.5, color: "var(--muted)" }}>
            {row.PlanHandle.slice(0, 18)}… · {row.ExecutionCount.toLocaleString()} calls · {row.DatabaseName}
          </span>
        </div>
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 16, alignItems: "flex-start" }}>
        <div style={{ flex: "1 1 520px", minWidth: 0, display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="panel-card" style={{ overflow: "hidden" }}>
            <div style={{ padding: "12px 17px", borderBottom: "1px solid var(--line)" }} className="th-label">
              STATEMENT
            </div>
            <pre className="mono" style={{ margin: 0, padding: "16px 19px", fontSize: 12, lineHeight: 1.85, whiteSpace: "pre-wrap" }}>{row.QueryText}</pre>
          </div>

          <div className="panel-card" style={{ overflowX: "auto" }}>
            <div style={{ padding: "13px 17px", borderBottom: "1px solid var(--line)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span style={{ font: "500 13.5px 'Space Grotesk', sans-serif" }}>Plan, estimated time by operator</span>
              {plan?.avg_elapsed_ms !== undefined && (
                <span className="mono" style={{ fontSize: 10.5, color: "var(--muted)" }}>{plan.avg_elapsed_ms.toFixed(1)}ms avg</span>
              )}
            </div>
            {plan === undefined && <div className="table-empty">Loading plan…</div>}
            {plan === null && <div className="table-empty">Plan unavailable.</div>}
            {plan && !plan.available && <div className="table-empty">No cached plan found for this statement.</div>}
            {plan?.available &&
              plan.nodes.map((n: PlanNode, i: number) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 17px", borderBottom: "1px solid var(--line2)" }}>
                  <span style={{ flex: "none", width: n.depth * 14 }} />
                  <span className="mono" style={{ flex: "none", fontSize: 11.5, color: n.cost_share > 0.5 ? statusColorVar("CRITICAL") : "var(--text)" }}>
                    {n.physical_op}
                  </span>
                  <span style={{ flex: 1, fontSize: 10.5, color: "var(--muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {n.logical_op} {n.estimated_rows ? `· ~${Number(n.estimated_rows).toLocaleString()} rows` : ""}
                  </span>
                  <div style={{ flex: "none", width: 120, height: 5, borderRadius: 3, background: "var(--soft)", overflow: "hidden" }}>
                    <div style={{ height: "100%", width: `${n.cost_share * 100}%`, background: n.cost_share > 0.5 ? statusColorVar("CRITICAL") : "var(--accent)", borderRadius: 3 }} />
                  </div>
                  <span className="mono" style={{ flex: "none", width: 60, fontSize: 11.5, textAlign: "right" }}>{n.estimated_time_ms.toFixed(1)}ms</span>
                </div>
              ))}
            <div style={{ padding: "8px 17px", fontSize: 10.5, color: "var(--muted)" }}>
              Time per operator is allocated proportionally by the plan's own cost estimate — not independently measured.
            </div>
          </div>
        </div>

        <div className="panel-card" style={{ flex: "1 1 290px", minWidth: 280, padding: 17, display: "flex", flexDirection: "column", gap: 14 }}>
          <span className="th-label">THIS STATEMENT</span>
          {[
            ["Avg elapsed", `${row.AvgElapsedTimeMs.toFixed(1)}ms`],
            ["Avg CPU", `${row.AvgCpuTimeMs.toFixed(1)}ms`],
            ["Avg logical reads", row.AvgLogicalReads.toLocaleString()],
            ["Calls", row.ExecutionCount.toLocaleString()],
            ["Max elapsed", `${row.MaxElapsedTimeMs.toFixed(1)}ms`],
            ["Last execution", new Date(row.LastExecutionTime).toLocaleString()],
          ].map(([label, value]) => (
            <div key={label} style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12 }}>
              <span style={{ fontSize: 12.5, color: "var(--muted)" }}>{label}</span>
              <span className="mono" style={{ fontSize: 12.5 }}>{value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function SqlTab({ instanceName }: { instanceName: string }) {
  const { data, loading, error } = useInstanceTab(instanceName, "sql");
  const [selected, setSelected] = useState<TopQueryRow | null>(null);

  if (loading) return <div className="page-loading">Loading…</div>;
  if (error) return <div className="banner-error">{error}</div>;

  const rows = (data?.top_queries?.data as unknown as TopQueryRow[] | null) ?? [];

  if (selected) {
    return <PlanDetail instanceName={instanceName} row={selected} onBack={() => setSelected(null)} />;
  }

  if (data?.top_queries?.error) return <div className="banner-error">{data.top_queries.error}</div>;
  if (rows.length === 0) return <div className="table-empty">No query stats found in the plan cache.</div>;

  return (
    <div className="panel-card" style={{ overflowX: "auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 18px", borderBottom: "1px solid var(--line)" }}>
        <span style={{ font: "500 13.5px 'Space Grotesk', sans-serif" }}>Top statements by average elapsed time</span>
        <span className="mono" style={{ fontSize: 10.5, color: "var(--muted)" }}>click a row to open the plan</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1.8fr 92px 88px 92px", padding: "9px 18px", borderBottom: "1px solid var(--line)" }}>
        <span className="th-label">STATEMENT</span>
        <span className="th-label th-label--right">AVG TIME</span>
        <span className="th-label th-label--right">CALLS</span>
        <span className="th-label th-label--right">READS</span>
      </div>
      {rows.map((r, i) => (
        <div
          key={i}
          onClick={() => setSelected(r)}
          style={{ display: "grid", gridTemplateColumns: "1.8fr 92px 88px 92px", alignItems: "center", padding: "12px 18px", borderBottom: "1px solid var(--line2)", cursor: "pointer" }}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 3, minWidth: 0, paddingRight: 20 }}>
            <span className="mono" style={{ fontSize: 11.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.QueryText}</span>
            <span className="mono" style={{ fontSize: 10.5, color: "var(--muted)" }}>{r.DatabaseName}</span>
          </div>
          <span className="mono" style={{ fontSize: 12, textAlign: "right", color: r.severity === "CRITICAL" ? statusColorVar("CRITICAL") : "var(--text)" }}>
            {r.AvgElapsedTimeMs.toFixed(0)}ms
          </span>
          <span className="mono" style={{ fontSize: 12, color: "var(--mid)", textAlign: "right" }}>{r.ExecutionCount.toLocaleString()}</span>
          <span className="mono" style={{ fontSize: 12, color: "var(--mid)", textAlign: "right" }}>{r.AvgLogicalReads.toFixed(0)}</span>
        </div>
      ))}
    </div>
  );
}
