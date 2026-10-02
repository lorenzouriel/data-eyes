import type { InstanceHealth, Severity } from "../types";
import { DIAGNOSTIC_CATEGORY_LABEL, orderedCategories, statusColorVar, statusLabel } from "../strata";

type Props =
  | { variant: "instance"; categories: Record<string, Severity> }
  | { variant: "fleet"; instances: InstanceHealth[] };

function Tile({ label, color, value, title }: { label: string; color: string; value: string; title: string }) {
  return (
    <div className="status-tile" style={{ borderLeftColor: color }} title={title}>
      <span className="status-tile-label">{label}</span>
      <span className="status-tile-value" style={{ color }}>{value}</span>
    </div>
  );
}

const SEVERITY_RANK: Record<Severity, number> = { CRITICAL: 0, WARNING: 1, UNKNOWN: 2, OK: 3 };

/** One tile per diagnostic category — an instance's own severities, or (in
 * fleet mode) a per-category count breakdown across every instance. Shares
 * one grid/Tile shell since only the value/color computation differs. */
export default function StatusSummaryPanel(props: Props) {
  if (props.variant === "instance") {
    const cats = orderedCategories(props.categories);
    return (
      <div className="status-tile-grid" aria-label="Health categories">
        {cats.map((cat) => {
          const sev = props.categories[cat];
          const label = DIAGNOSTIC_CATEGORY_LABEL[cat] ?? cat.replace(/_/g, " ");
          return (
            <Tile
              key={cat}
              label={label}
              color={statusColorVar(sev)}
              value={statusLabel(sev)}
              title={`${label}: ${sev}`}
            />
          );
        })}
      </div>
    );
  }

  const { instances } = props;
  const seen = new Set<string>();
  instances.forEach((i) => Object.keys(i.categories).forEach((c) => seen.add(c)));
  const cats = orderedCategories(Object.fromEntries([...seen].map((c) => [c, true])));

  return (
    <div className="status-tile-grid" aria-label="Fleet health categories">
      {cats.map((cat) => {
        const counts: Record<Severity, number> = { OK: 0, WARNING: 0, CRITICAL: 0, UNKNOWN: 0 };
        for (const instance of instances) {
          const sev = instance.categories[cat];
          if (sev) counts[sev] += 1;
        }
        const total = counts.OK + counts.WARNING + counts.CRITICAL + counts.UNKNOWN;
        const worst = (Object.keys(counts) as Severity[])
          .filter((s) => counts[s] > 0)
          .sort((a, b) => SEVERITY_RANK[a] - SEVERITY_RANK[b])[0] ?? "OK";
        const value =
          counts.WARNING + counts.CRITICAL + counts.UNKNOWN === 0
            ? `${counts.OK}/${total} OK`
            : ([
                counts.CRITICAL ? `${counts.CRITICAL} critical` : null,
                counts.WARNING ? `${counts.WARNING} warning` : null,
                counts.UNKNOWN ? `${counts.UNKNOWN} unknown` : null,
              ].filter(Boolean) as string[]).join(", ");
        const label = DIAGNOSTIC_CATEGORY_LABEL[cat] ?? cat.replace(/_/g, " ");
        return (
          <Tile
            key={cat}
            label={label}
            color={statusColorVar(worst)}
            value={value}
            title={`${label}: ${value} of ${total} instances`}
          />
        );
      })}
    </div>
  );
}
