# Blocking Chain Snapshot

**Script:** `blocking_chain_snapshot.sql` · **MCP tool:** `blocking_snapshot()`

## Purpose

Point-in-time view of active blocking, instance-wide, with head-blocker identification — feeds the Sessions/Blocking tab and Step 3 (Contention) of the performance methodology.

## Output columns

`BlockedSessionID`, `BlockingSessionID`, `WaitType`, `WaitTimeSeconds`, `WaitResource`, `DatabaseName`, `BlockedLoginName`, `BlockedHostName`, `BlockedQueryText`, `BlockingSessionIsHeadBlocker` (1 if `BlockingSessionID` is not itself blocked by anything — the root cause of the chain), `severity`.

## Severity logic

`WaitTimeSeconds ≥ 120` → `CRITICAL`; `≥ 30` → `WARNING`. See `.claude/knowledge-base/_static/thresholds.yaml` (`waits.blocking_duration_seconds`).

## Notes

This is a snapshot, not a trend — a single call only catches blocking active at that instant. For the dashboard's background poller (§4 of the rearchitecture plan), call this repeatedly to detect persistent vs. transient blocking.
