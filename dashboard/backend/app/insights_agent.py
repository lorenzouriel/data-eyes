"""
Embedded real-time insights agent.

Genuinely part of the dashboard's request/response and polling cycle — not a
bolted-on iframe. Reuses the same severity-tagged MCP JSON the page is already
fetching (no duplicate diagnostic queries); the LLM's job is only to turn that
JSON into 1-3 sentences of commentary.

Model tiering (per the rearchitecture plan, approved by the user): a fast/
cheap model (Claude Haiku 4.5) for routine commentary — both the on-page-load
stream and the background severity-change sweep (see insights_sweep.py) —
reserving a stronger model (Claude Opus 5) for on-demand "explain this in
depth" requests only. This is the primary cost/latency lever for this
feature; tune the model/prompt against real usage, not in advance.
"""

import json
import logging
from typing import AsyncIterator, Optional

from anthropic import AsyncAnthropic

from .config import settings

logger = logging.getLogger(__name__)

# Haiku 4.5 does not support output_config.effort (errors if set) or adaptive
# thinking — omit both for routine calls. Opus 5 gets an explicit effort on
# the deep-explanation path since it's a single-turn task, not the hardest
# agentic/coding case the "xhigh" guidance targets.
_ROUTINE_MODEL = "claude-haiku-4-5"
_DEEP_MODEL = "claude-opus-5"

_SYSTEM_PROMPT = (
    "You are a terse SQL Server monitoring assistant embedded in a DBA "
    "dashboard. You are given severity-tagged diagnostic data already "
    "computed by the monitoring system — you do not have access to the "
    "database yourself, and you must never invent numbers not present in "
    "the data. Point out what's actually wrong or notably fine, in plain "
    "language a DBA can act on. Never restate the raw data verbatim."
)

_client: Optional[AsyncAnthropic] = None


def _get_client() -> Optional[AsyncAnthropic]:
    global _client
    if not settings.ANTHROPIC_API_KEY:
        return None
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


def _compact_context(context: dict) -> str:
    """Summarize row counts and severities rather than dumping full result
    sets — keeps the prompt small and the model's job (commentary, not
    transcription) unambiguous."""
    lines = []
    for key, value in context.items():
        if isinstance(value, list):
            severities = [row.get("severity") for row in value if isinstance(row, dict) and row.get("severity")]
            worst = next((s for s in ("CRITICAL", "WARNING") if s in severities), "OK")
            lines.append(f"{key}: {len(value)} row(s), worst severity {worst}")
            notable = [row for row in value if isinstance(row, dict) and row.get("severity") in ("CRITICAL", "WARNING")][:5]
            if notable:
                lines.append(f"  notable rows: {json.dumps(notable, default=str)}")
        elif isinstance(value, dict):
            lines.append(f"{key}: {json.dumps(value, default=str)}")
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines) if lines else "(no data)"


async def stream_insight(context: dict) -> AsyncIterator[str]:
    """1-3 sentence commentary on a page's already-fetched data, streamed.
    Yields nothing if ANTHROPIC_API_KEY isn't configured or the call fails —
    the insights feed is an enhancement, never a requirement to use the
    dashboard."""
    client = _get_client()
    if client is None:
        return
    prompt = (
        "Here is the current diagnostic data for this view:\n\n"
        f"{_compact_context(context)}\n\n"
        "In 1-3 sentences, tell the DBA what matters here. If everything is "
        "OK, say so briefly rather than listing every metric."
    )
    try:
        async with client.messages.stream(
            model=_ROUTINE_MODEL,
            max_tokens=300,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            async for text in stream.text_stream:
                yield text
    except Exception:
        logger.exception("Insight generation failed")
        return


async def generate_severity_change_insight(
    instance_name: str, category: str, old_severity: str, new_severity: str, context: dict
) -> Optional[str]:
    """Called by the background sweep only when a category's severity
    actually changed since the previous sweep — bounds LLM cost against a
    fleet whose data is otherwise polled continuously. Non-streaming: this is
    stored for the insights feed, not rendered live to a waiting user."""
    client = _get_client()
    if client is None:
        return None
    prompt = (
        f"On instance '{instance_name}', the '{category}' category changed "
        f"from {old_severity} to {new_severity}.\n\n"
        f"Current data:\n{_compact_context(context)}\n\n"
        "In 1-2 sentences, explain what changed and whether it needs attention."
    )
    try:
        response = await client.messages.create(
            model=_ROUTINE_MODEL,
            max_tokens=200,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return text or None
    except Exception:
        logger.exception("Severity-change insight generation failed")
        return None


async def stream_deep_explanation(context: dict, question: Optional[str] = None) -> AsyncIterator[str]:
    """On-demand "explain this in depth" — the one path that uses the
    stronger model, gated behind explicit user action so its higher cost is
    never incurred by routine polling or the background sweep."""
    client = _get_client()
    if client is None:
        return
    user_question = question or "Explain what's happening here in depth, and what I should do about it."
    prompt = (
        "Here is the current diagnostic data for this view:\n\n"
        f"{_compact_context(context)}\n\n"
        f"{user_question}"
    )
    try:
        async with client.messages.stream(
            model=_DEEP_MODEL,
            max_tokens=2000,
            system=_SYSTEM_PROMPT,
            output_config={"effort": "medium"},
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            async for text in stream.text_stream:
                yield text
    except Exception:
        logger.exception("Deep explanation generation failed")
        return
