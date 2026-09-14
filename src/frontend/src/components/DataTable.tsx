import StatusBadge from "./StatusBadge";
import type { Severity } from "../types";

function isSeverity(value: unknown): value is Severity {
  return value === "OK" || value === "WARNING" || value === "CRITICAL" || value === "UNKNOWN";
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

// DMV result sets are wide and shape varies per tool — a plain table (columns
// = keys of the first row) is the right form here, not a chart: this is
// tabular diagnostic data, not a trend over time (dataviz skill, choosing-a-form:
// "sometimes the answer is not a chart").
export default function DataTable({ rows }: { rows: Record<string, unknown>[] | null | undefined }) {
  if (!rows || rows.length === 0) {
    return <div className="table-empty">No rows.</div>;
  }
  const columns = Object.keys(rows[0]);
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col}>{col}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {columns.map((col) => {
                const value = row[col];
                if (col.toLowerCase() === "severity" && isSeverity(value)) {
                  return (
                    <td key={col}>
                      <StatusBadge severity={value} />
                    </td>
                  );
                }
                return <td key={col}>{formatCell(value)}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
