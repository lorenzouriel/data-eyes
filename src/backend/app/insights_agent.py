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
from typing import AsyncIterator, Dict, List, Optional

from anthropic import AsyncAnthropic
from pydantic import BaseModel

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


# ---------------------------------------------------------------------------
# Advisor — structured, on-demand root-cause narration over one instance's
# real diagnostic data (wait history, blocking chain, top query + its parsed
# plan, missing-index candidates). Deliberately NOT the mock design's
# "shadow-tested" / "modelled impact" claims: nothing here is validated or
# benchmarked, only drafted from live evidence. estimated_impact must be
# sourced from missing_indexes()'s own improvement-score numbers, never
# fabricated — enforced by prompt instruction, not by code (there is no
# reliable way to verify a free-text field's provenance after the fact).
# ---------------------------------------------------------------------------


class AdvisorTimelineStep(BaseModel):
    stage: str
    detail: str


class AdvisorFinding(BaseModel):
    # Stable id for this finding so a re-generated report can still match it
    # against a previously-dismissed one (see repository.advisor_dismissal).
    # Should stay the same across regenerations of the same underlying issue
    # (e.g. derived from the table/column/wait-category it's about) — the
    # model is instructed to do this, not code-enforced.
    finding_key: str
    title: str
    severity: str
    timeline: List[AdvisorTimelineStep]
    proposed_ddl: Optional[str] = None
    risks: List[str]
    evidence: List[str]
    estimated_impact: Optional[str] = None


class AdvisorReport(BaseModel):
    summary: str
    findings: List[AdvisorFinding]


_ADVISOR_SYSTEM_PROMPT = (
    "You are a SQL Server performance advisor embedded in a DBA dashboard. "
    "You are given real, already-computed diagnostic data for one instance: "
    "wait-category history, the current blocking chain, the instance's "
    "top-cost query and its execution plan (per-operator time there is "
    "cost-derived from the plan's own cost estimates, not independently "
    "measured — treat it as approximate), and missing-index candidates "
    "computed from live DMV statistics. Draft at most 3 concrete findings, "
    "worst first, each with a finding_key that is a short stable slug "
    "derived from what the finding is about (e.g. the table/index name or "
    "wait category), a short timeline of stages 'detected', 'correlated', "
    "'analyzed', 'attributed', 'drafted' showing how you reasoned from "
    "symptom to cause, a proposed_ddl ONLY when a specific missing-index "
    "candidate in the data directly supports one (never invent an index "
    "that isn't in the data; leave proposed_ddl null otherwise), concrete "
    "risks of applying that DDL, and the evidence rows that led you there. "
    "For estimated_impact, use ONLY the improvement-score/user-impact "
    "numbers already present in the missing-index data, phrased as an "
    "estimate (e.g. 'DMV improvement score: 84,200 — an estimate, not a "
    "measured result'). Never say a change was shadow-tested, modelled, "
    "validated, or benchmarked — nothing here has been applied. If the data "
    "shows nothing actionable, return an empty findings list and say so "
    "plainly in the summary."
)


async def generate_advisor_report(instance_name: str, context: dict) -> Optional[AdvisorReport]:
    """Non-streaming, structured JSON output via messages.parse — the report
    is generated fresh on every call (see routers/insights.py), not cached,
    so it always reflects the instance's current data."""
    client = _get_client()
    if client is None:
        return None
    prompt = (
        f"Instance: {instance_name}\n\n"
        f"{_compact_context(context)}\n\n"
        "Draft the advisor findings for this instance now."
    )
    try:
        response = await client.messages.parse(
            model=_DEEP_MODEL,
            max_tokens=4096,
            system=_ADVISOR_SYSTEM_PROMPT,
            output_config={"effort": "medium"},
            messages=[{"role": "user", "content": prompt}],
            output_format=AdvisorReport,
        )
        return response.parsed_output
    except Exception:
        logger.exception("Advisor report generation failed for %s", instance_name)
        return None


# ---------------------------------------------------------------------------
# Ask the fleet — real multi-turn chat (conversation history is sent back on
# every turn, same statelessness as the rest of the Messages API) over
# fleet-wide health data, not a single-shot Q&A.
# ---------------------------------------------------------------------------

_ASK_SYSTEM_PROMPT = (
    "You are the Data Eyes fleet assistant, answering a DBA's plain-English "
    "questions about their registered SQL Server instances. You are given "
    "severity-tagged health data already computed by the monitoring system "
    "— you do not query the databases yourself, and must never invent "
    "numbers not present in the data. If the data needed to answer isn't in "
    "the context provided, say so plainly instead of guessing. Be direct "
    "and specific, and name instances explicitly when relevant."
)


async def stream_chat(history: List[Dict[str, str]], context: dict) -> AsyncIterator[str]:
    """history is the full conversation so far, each item {"role": "user"|
    "assistant", "content": str} — real multi-turn state, not a single
    prompt. context is fleet-wide health data, recompacted fresh on every
    call by the caller (see routers/insights.py's /ask) since fleet state
    can change between turns."""
    client = _get_client()
    if client is None or not history:
        return
    system = f"{_ASK_SYSTEM_PROMPT}\n\nCurrent fleet data:\n{_compact_context(context)}"
    messages = [{"role": item["role"], "content": item["content"]} for item in history]
    try:
        async with client.messages.stream(
            model=_DEEP_MODEL,
            max_tokens=2000,
            system=system,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text
    except Exception:
        logger.exception("Fleet chat generation failed")
        return
