"""
Small Streamlit client for the internal agent API.
"""
import json
import os

import httpx
import streamlit as st

API_URL = os.getenv("AGENT_API_URL", "http://localhost:8000").rstrip("/")


def events(lines):
    """Decode SSE frames, ignoring comments and empty frames."""
    kind, data = "message", []
    for line in lines:
        if not line:
            if data:
                yield kind, json.loads("\n".join(data))
            kind, data = "message", []
        elif line.startswith("event:"):
            kind = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip())


def main():
    st.set_page_config(page_title="Data Eyes | Ask the fleet", page_icon="👁", layout="centered")
    st.title("Ask the fleet")
    st.caption("Data Eyes · Your SQL Server fleet assistant")
    if "messages" not in st.session_state:
        st.session_state.messages = []
    current = None
    with st.sidebar:
        st.header("Data Eyes")
        try:
            response = httpx.get(f"{API_URL}/api/agent/status", timeout=5)
            response.raise_for_status()
            current = response.json()
        except (httpx.HTTPError, ValueError):
            st.error("Cannot reach the agent. Check that the API is running.")
        if current:
            st.caption("Model provider")
            st.write(current["provider_label"])
            st.caption(current["model"] or "No model configured")
            st.caption("Collector metrics via MCP" if current["monitoring_configured"] else "Monitoring access not configured")
            if not current["configured"]:
                st.warning(current["reason"])
        if st.button("New chat", use_container_width=True):
            st.session_state.messages = []
        st.button("Refresh connection", use_container_width=True)
        st.caption("History is kept only for this browser session. The latest 19 exchanges are sent with each question.")

    if not st.session_state.messages:
        st.info("Ask about fleet health, performance, blocking, or backups.")
        st.caption('Try: "Which instances need attention?" or "Show blocking on my instance."')
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("error"):
                st.error(message["error"])

    prompt = st.chat_input("Ask about your SQL Server fleet…", max_chars=8000,
                           disabled=not (current and current["configured"]))
    if not prompt or not prompt.strip():
        return
    # Send complete exchanges within the API's 40-message/8000-character limits.
    history = []
    messages = st.session_state.messages
    for index in range(0, len(messages) - 1, 2):
        question, reply = messages[index:index + 2]
        if not reply.get("error"):
            history.extend({"role": m["role"], "content": m["content"][:8000]} for m in (question, reply))
    question = {"role": "user", "content": prompt.strip()}
    history = history[-38:] + [question]
    messages.append(question)
    with st.chat_message("user"):
        st.markdown(question["content"])
    reply = {"role": "assistant", "content": ""}
    messages.append(reply)
    with st.chat_message("assistant"):
        progress = st.status("Checking the fleet…", expanded=False)
        output = st.empty()
        try:
            # Idle timeout between events; a question may need several model calls.
            with httpx.stream("POST", f"{API_URL}/api/agent/ask", json={"messages": history},
                              timeout=httpx.Timeout(300, connect=5)) as response:
                response.raise_for_status()
                completed = False
                for kind, payload in events(response.iter_lines()):
                    if kind == "status":
                        progress.update(label=payload["text"])
                    elif kind == "text":
                        reply["content"] += payload["text"]
                        output.markdown(reply["content"])
                    elif kind == "error":
                        reply["error"] = payload["error"]
                    elif kind == "done":
                        completed = True
                        break
                if not completed:
                    reply["error"] = "The connection ended before the answer finished. Please try again."
                elif not reply["content"] and not reply.get("error"):
                    reply["error"] = "The agent returned no answer. Please try again."
        except httpx.HTTPStatusError as exc:
            reply["error"] = {
                429: "The assistant is busy. Please try again in a moment.",
                503: "The agent is not configured. Check its provider settings and refresh the connection.",
            }.get(exc.response.status_code, "The agent could not answer this request. Please try again.")
        except (httpx.HTTPError, ValueError, KeyError):
            reply["error"] = "The agent connection failed. Check the API and try again."
        if reply.get("error"):
            progress.update(label="Unable to complete the answer", state="error")
            st.error(reply["error"])
        else:
            progress.update(label="Complete", state="complete")


if __name__ == "__main__":
    main()
