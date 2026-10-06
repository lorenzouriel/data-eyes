import { useInstanceTab } from "../../hooks/useInstanceTab";

interface DatabaseStatus {
  name: string;
  state: string;
  updateability: string | null;
  in_availability_group: boolean;
  availability_group: string | null;
  replica_role: string | null;
}

export default function DatabasesTab({ instanceName }: { instanceName: string }) {
  const { data, loading, error } = useInstanceTab(instanceName, "databases");
  if (loading) return <div className="page-loading">Loading database status…</div>;
  const failure = error || data?.databases?.error;
  if (failure) return <div className="banner-error">{failure}</div>;
  const rows = (data?.databases?.data as unknown as DatabaseStatus[]) ?? [];
  return (
    <div className="panel-card" style={{ overflowX: "auto" }}>
      <table className="database-status-table">
        <thead><tr>{["Database", "State", "Access mode", "Always On AG", "Availability group", "Local replica"].map(label => <th key={label}>{label}</th>)}</tr></thead>
        <tbody>{rows.map(db => <tr key={db.name}>
          <td className="mono">{db.name}</td><td>{db.state}</td>
          <td>{db.updateability === "READ_ONLY" ? "Read only" : db.updateability === "READ_WRITE" ? "Read/write" : "Unknown"}</td>
          <td>{db.in_availability_group ? "Yes" : "No"}</td>
          <td>{db.availability_group ?? (db.in_availability_group ? "Unknown" : "—")}</td>
          <td>{db.replica_role ?? (db.in_availability_group ? "Unknown" : "—")}</td>
        </tr>)}</tbody>
      </table>
      {rows.length === 0 && <div className="table-empty">No visible databases.</div>}
    </div>
  );
}
