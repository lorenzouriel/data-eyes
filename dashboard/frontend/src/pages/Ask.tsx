import { useEffect, useRef, useState } from "react";
import AppShell from "../components/AppShell";
import { streamAsk, ApiError } from "../api";
import type { ChatMessage } from "../types";

const SUGGESTED_PROMPTS = [
  "Which instances are critical right now?",
  "Summarize wait time across the fleet.",
  "What needs attention before I sign off today?",
];

export default function Ask() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  const send = async (text: string) => {
    const question = text.trim();
    if (!question || sending) return;

    setError(null);
    const history = [...messages, { role: "user" as const, content: question }];
    setMessages([...history, { role: "assistant", content: "" }]);
    setInput("");
    setSending(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamAsk(
        history,
        (chunk) => {
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            next[next.length - 1] = { ...last, content: last.content + chunk };
            return next;
          });
        },
        controller.signal,
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The fleet assistant is unavailable right now.");
    } finally {
      setSending(false);
    }
  };

  return (
    <AppShell active="ask">
      <div className="page-inner" style={{ maxWidth: 860 }}>
        <div className="page-header-row">
          <div>
            <h1 className="page-title">Ask the fleet</h1>
            <p className="page-subtitle">Plain-English questions over your registered instances' live health data.</p>
          </div>
        </div>

        {error && <div className="banner-error">{error}</div>}

        <div className="panel-card" style={{ display: "flex", flexDirection: "column", minHeight: 420, padding: 0 }}>
          <div style={{ flex: 1, padding: "18px 20px", display: "flex", flexDirection: "column", gap: 16, overflowY: "auto", maxHeight: 520 }}>
            {messages.length === 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <span style={{ fontSize: 13, color: "var(--muted)" }}>Try asking:</span>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {SUGGESTED_PROMPTS.map((p) => (
                    <button
                      key={p}
                      className="btn-ghost"
                      style={{ textAlign: "left", width: "fit-content" }}
                      onClick={() => send(p)}
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((m, i) => (
              <div
                key={i}
                style={{
                  alignSelf: m.role === "user" ? "flex-end" : "flex-start",
                  maxWidth: "82%",
                  padding: "10px 14px",
                  borderRadius: 10,
                  fontSize: 13.5,
                  lineHeight: 1.6,
                  whiteSpace: "pre-wrap",
                  background: m.role === "user" ? "var(--accentSoft)" : "var(--soft)",
                  color: "var(--text)",
                }}
              >
                {m.content || (sending && i === messages.length - 1 ? "…" : "")}
              </div>
            ))}
            <div ref={bottomRef} />
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
            style={{ display: "flex", gap: 10, padding: 14, borderTop: "1px solid var(--line)" }}
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about your fleet…"
              disabled={sending}
              style={{
                flex: 1,
                padding: "9px 12px",
                borderRadius: 8,
                border: "1px solid var(--line)",
                background: "var(--bg)",
                color: "var(--text)",
                fontSize: 13.5,
                fontFamily: "inherit",
              }}
            />
            <button className="btn-primary" type="submit" disabled={sending || !input.trim()}>
              {sending ? "Thinking…" : "Send"}
            </button>
          </form>
        </div>
      </div>
    </AppShell>
  );
}
