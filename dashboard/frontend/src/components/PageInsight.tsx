import { useEffect, useRef, useState } from "react";

// Streams the embedded agent's on-page-load commentary (app/insights_agent.py
// stream_insight, routine model) via SSE. Remounts its stream whenever
// streamUrl changes — e.g. switching drill-down tabs — because each URL is
// scoped to different context data on the backend. Stays invisible if no
// insight ever arrives (no ANTHROPIC_API_KEY configured degrades to an
// immediate "done" with zero text — that's a silent no-op, not an error).
export default function PageInsight({ streamUrl }: { streamUrl: string }) {
  const [text, setText] = useState("");
  const [streaming, setStreaming] = useState(true);
  const textRef = useRef("");

  useEffect(() => {
    textRef.current = "";
    setText("");
    setStreaming(true);

    const source = new EventSource(streamUrl, { withCredentials: true });

    source.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (typeof payload.text === "string") {
          textRef.current += payload.text;
          setText(textRef.current);
        }
      } catch {
        // Malformed frame — ignore rather than surfacing a broken UI over an
        // optional, best-effort feature.
      }
    };

    source.addEventListener("done", () => {
      setStreaming(false);
      source.close();
    });

    source.onerror = () => {
      setStreaming(false);
      source.close();
    };

    return () => {
      source.close();
    };
  }, [streamUrl]);

  if (!text && !streaming) return null;

  return (
    <div className="page-insight">
      <span className="page-insight-icon" aria-hidden="true">
        ◆
      </span>
      <div className="page-insight-body">
        <span className="page-insight-label">Insight</span>
        <p className="page-insight-text">
          {text || (streaming ? "Analyzing…" : "")}
          {streaming && <span className="page-insight-cursor" aria-hidden="true" />}
        </p>
      </div>
    </div>
  );
}
