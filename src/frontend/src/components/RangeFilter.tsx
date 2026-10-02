export type RangeMode = "30d" | "7d" | "day";

export interface RangeValue {
  mode: RangeMode;
  day: string; // ISO yyyy-mm-dd, only meaningful when mode === "day"
}

// Local calendar date (not UTC), so evenings west of UTC don't roll to tomorrow.
export function todayIso(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const date = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${date}`;
}

const OPTIONS: { mode: RangeMode; label: string }[] = [
  { mode: "30d", label: "Last 30 days" },
  { mode: "7d", label: "Last 7 days" },
  { mode: "day", label: "Pick a day" },
];

// "Last 30 days / Last 7 days / Pick a day" — the 30d/7d modes drive a
// day-bucketed Top-10 chart, "Pick a day" switches to the raw drill-down log
// for that single calendar day (see TopActivityTab).
export default function RangeFilter({ value, onChange }: { value: RangeValue; onChange: (next: RangeValue) => void }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
      <div style={{ display: "flex" }}>
        {OPTIONS.map((opt, i) => (
          <button
            key={opt.mode}
            onClick={() => onChange({ mode: opt.mode, day: value.day || todayIso() })}
            style={{
              font: "500 11.5px 'Space Grotesk', sans-serif",
              padding: "6px 12px",
              border: `1px solid ${value.mode === opt.mode ? "var(--accent)" : "var(--line)"}`,
              background: value.mode === opt.mode ? "var(--accentSoft)" : "var(--panel)",
              color: value.mode === opt.mode ? "var(--accent)" : "var(--mid)",
              cursor: "pointer",
              borderRadius: i === 0 ? "7px 0 0 7px" : i === OPTIONS.length - 1 ? "0 7px 7px 0" : 0,
            }}
          >
            {opt.label}
          </button>
        ))}
      </div>
      {value.mode === "day" && (
        <input
          type="date"
          value={value.day || todayIso()}
          max={todayIso()}
          onChange={(e) => onChange({ mode: "day", day: e.target.value || todayIso() })}
          style={{
            font: "500 11.5px 'JetBrains Mono', monospace",
            padding: "6px 10px",
            border: "1px solid var(--line)",
            borderRadius: 7,
            background: "var(--panel)",
            color: "var(--text)",
          }}
        />
      )}
    </div>
  );
}
