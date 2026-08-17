import { useEffect, useState } from "react";
import { getInsightsFeed } from "../api";
import type { Insight } from "../types";
import StatusBadge from "./StatusBadge";

const POLL_INTERVAL_MS = 30_000;

function formatWhen(iso: string): string {
  return new Date(iso).toLocaleString();
}

// Renders app/insights_sweep.py's severity-change history (GET
// /api/insights/feed). Polls rather than streams — this is a bounded ring
// buffer of past events, not a live generation, so a plain refresh interval
// matches MainPage's fleet-health polling instead of needing SSE.
export default function InsightsFeed() {
  const [insights, setInsights] = useState<Insight[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      getInsightsFeed()
        .then((res) => {
          if (!cancelled) setInsights(res.insights);
        })
        .catch(() => {
          // Bonus panel — a failed poll just leaves the previous state (or
          // stays hidden) rather than surfacing a page-wide error banner.
        });
    };
    load();
    const id = setInterval(load, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  // No key configured, or nothing has changed severity yet — stay invisible.
  if (!insights || insights.length === 0) return null;

  return (
    <section className="insights-feed">
      <h2 className="insights-feed-title">Recent Insights</h2>
      <ul className="insights-feed-list">
        {insights.map((insight, i) => (
          <li key={i} className="insights-feed-item">
            <StatusBadge severity={insight.severity} />
            <div className="insights-feed-item-body">
              <div className="insights-feed-item-meta">
                <span className="insights-feed-item-instance">{insight.instance_name}</span>
                <span className="insights-feed-item-category">{insight.category}</span>
                <span className="insights-feed-item-time">{formatWhen(insight.created_at)}</span>
              </div>
              <p className="insights-feed-item-message">{insight.message}</p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
