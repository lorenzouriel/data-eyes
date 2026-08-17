import { useEffect, useRef, useState } from "react";
import { streamExplain } from "../api";

// On-demand deep explanation — the one path that uses the stronger model
// (app/insights_agent.py stream_deep_explanation), gated behind explicit
// user action rather than firing automatically like PageInsight/InsightsFeed.
export default function ExplainPanel({
  instanceName,
  databaseName,
  tabName,
}: {
  instanceName: string;
  databaseName: string;
  tabName: string;
}) {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => controllerRef.current?.abort();
  }, []);

  // Switching tabs invalidates any in-flight or previously shown explanation
  // for the old tab — closing rather than silently reusing stale context.
  useEffect(() => {
    controllerRef.current?.abort();
    setOpen(false);
    setText("");
    setError(null);
    setLoading(false);
  }, [instanceName, databaseName, tabName]);

  const run = async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    setText("");
    setError(null);
    setLoading(true);
    try {
      await streamExplain(
        {
          instance_name: instanceName,
          database_name: databaseName,
          tab_name: tabName,
          question: question.trim() || undefined,
        },
        (chunk) => setText((prev) => prev + chunk),
        controller.signal,
      );
    } catch (err) {
      if (!controller.signal.aborted) {
        setError(err instanceof Error ? err.message : "Failed to load explanation");
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  };

  if (!open) {
    return (
      <button className="btn-ghost explain-toggle" onClick={() => setOpen(true)}>
        Explain in depth
      </button>
    );
  }

  return (
    <div className="explain-panel">
      <div className="explain-panel-header">
        <span className="explain-panel-title">Explain in depth</span>
        <button
          className="btn-ghost"
          onClick={() => {
            controllerRef.current?.abort();
            setOpen(false);
          }}
        >
          Close
        </button>
      </div>

      <div className="explain-panel-form">
        <input
          className="explain-panel-input"
          type="text"
          placeholder="Optional: ask a specific question about this tab…"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !loading) run();
          }}
        />
        <button className="btn-primary" onClick={run} disabled={loading}>
          {loading ? "Thinking…" : "Explain"}
        </button>
      </div>

      {error && <div className="banner-error">{error}</div>}

      {(text || loading) && (
        <p className="explain-panel-text">
          {text || "Analyzing…"}
          {loading && <span className="page-insight-cursor" aria-hidden="true" />}
        </p>
      )}
    </div>
  );
}
