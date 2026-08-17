import DataTable from "./DataTable";
import type { TabResult } from "../types";

export default function TabSection({ title, result }: { title: string; result?: TabResult }) {
  return (
    <section className="tab-section">
      <h3>{title}</h3>
      {!result && <div className="page-loading">Loading…</div>}
      {result?.error && <div className="banner-error">{result.error}</div>}
      {result && !result.error && <DataTable rows={result.data} />}
    </section>
  );
}
