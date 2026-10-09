"""Scheduled SQL collection, bounded labels, persistent check watermarks.

Two loops per instance: the fast metric cycle (app.metrics) and the alert
check cycle (app.alerts). Results are cached in memory; a Prometheus scrape
only reads the cache and never runs SQL.

Severity encoding is ordered: OK=0, UNKNOWN=1, WARNING=2, CRITICAL=3.
SQL text, session identities and event bodies are never metric labels.
"""
import asyncio
import copy
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily

from app import metrics
from app.alerts.catalog import CATALOG, TIER_SECONDS
from app.alerts.checks import CHECKS
from app.alerts.evaluation import confirm, effective_setting, is_excluded, item_severity, summarize
from app.alerts.models import CheckContext
from app.config import settings
from app.metrics import metric
from app.sql import QueryLimitExceeded, query, query_lane

LOG = logging.getLogger(__name__)
RANK = {"OK": 0, "UNKNOWN": 1, "WARNING": 2, "CRITICAL": 3}


class Exporter:
    def __init__(self, instances, overrides, state_path=None):
        self.instances, self.overrides = instances, overrides
        self.path = Path(state_path or settings.STATE_FILE)
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.samples = {}
        self.next_run = {}
        self.semaphore = asyncio.Semaphore(settings.SQL_MAX_CONCURRENT_QUERIES)
        for instance in instances:
            groups = {"connection": 0, **{group: every or settings.COLLECTOR_INTERVAL_SECONDS for group, _, every in metrics.GROUPS}}
            for definition in self.enabled_checks(instance):
                groups["alert." + definition.key] = TIER_SECONDS[effective_setting(definition, overrides, instance.name).tier]
            for group, interval in groups.items():
                self.samples[(instance.name, group)] = dict(attempt=0, last_success=0, ttl=max(interval * 2 + 60, 120), duration=0, ok=False, rows=[])

    def enabled_checks(self, instance):
        return [definition for definition in CATALOG
                if definition.key in CHECKS and definition.key != "sql_server_connection"
                and effective_setting(definition, self.overrides, instance.name).enabled]

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.state), encoding="utf-8")
        os.replace(temp, self.path)

    def collect(self):
        """prometheus_client custom collector: render the cached samples."""
        families = {}
        now = time.time()
        for instance in self.instances:
            severities = []
            for (name, group), entry in list(self.samples.items()):
                if name != instance.name:
                    continue
                base = {"sql_instance": name, "environment": instance.environment}
                fresh = now - entry["attempt"] <= entry["ttl"]
                rows = metric("collection_success", int(entry["ok"] and fresh), {"collector": group})
                rows += metric("collection_last_success_timestamp_seconds", entry["last_success"], {"collector": group})
                rows += metric("collection_duration_seconds", entry["duration"], {"collector": group})
                if entry["ok"] and fresh:
                    rows += entry["rows"]
                if group == "connection":
                    reachable = int(entry["ok"] and fresh)
                    rows += metric("sqlserver_reachable", reachable)
                    severity = 0 if reachable else (3 if fresh else 1)
                    rows += metric("health_severity", severity, {"category": "alert.sql_server_connection"})
                    severities.append(severity)
                if group.startswith("alert."):
                    severity = entry.get("severity", 1) if entry["ok"] and fresh else 1
                    rows += metric("health_severity", severity, {"category": group})
                    severities.append(severity)
                for sample, value, labels, counter in rows:
                    combined = {**base, **labels}
                    keys = tuple(sorted(combined))
                    if sample not in families:
                        cls = CounterMetricFamily if counter else GaugeMetricFamily
                        families[sample] = cls(sample, sample.replace("_", " "), labels=keys)
                    families[sample].add_metric([combined[k] for k in keys], value)
            overall = max(severities) if severities else 1
            family = families.setdefault("data_eyes_overall_severity", GaugeMetricFamily(
                "data_eyes_overall_severity", "OK=0 Unknown=1 Warning=2 Critical=3", labels=["sql_instance", "environment"]))
            family.add_metric([instance.name, instance.environment], overall)
        yield from families.values()

    async def execute(self, instance, group, interval, function):
        """Run one group if it is due and cache its rows and severity."""
        key = (instance.name, group)
        now = time.time()
        if now < self.next_run.get(key, 0):
            return
        self.next_run[key] = now + interval
        old = self.samples.get(key, {})
        entry = dict(attempt=now, last_success=old.get("last_success", 0), ttl=max(interval * 2 + 60, 120), duration=0, ok=False, rows=[])
        start = time.monotonic()
        try:
            rows, severity = await function()
            entry.update(ok=True, rows=rows, severity=severity, last_success=time.time())
        except Exception as exc:
            # Do not log SQL, connection strings or diagnostic record bodies.
            LOG.warning("Collection failed instance=%s collector=%s error=%s", instance.name, group, type(exc).__name__)
            if isinstance(exc, QueryLimitExceeded):
                # The server already spent up to the full timeout on this query;
                # a one-minute retry would turn a heavy daily check into one
                # that runs 1,440 times a day. Retry within the hour instead.
                self.next_run[key] = time.time() + min(max(interval, 60), 3600)
            else:
                # A temporary queue/permission/connection failure should not defer a
                # daily diagnostic for another full day.
                self.next_run[key] = time.time() + min(max(interval, 30), 60)
        entry["duration"] = time.monotonic() - start
        self.samples[key] = entry

    async def check_rows(self, instance, definition, setting, cache=None):
        """Run one alert check; persist its watermarks; return rows and severity."""
        key = instance.name + ":" + definition.key
        previous = self.state.get(key, {})
        working = copy.deepcopy(previous)
        connection = instance.mssql_connection_string
        context = CheckContext(instance.name, connection, setting, working.setdefault("memory", {}), datetime.now(timezone.utc),
                               lambda sql: query(connection, sql), cache if cache is not None else {})
        if definition.key in ("database_corruption", "rebuild_failed"):
            available = await context.query("SELECT CASE WHEN OBJECT_ID(N'master.dbo.CommandLog') IS NULL THEN 0 ELSE 1 END AS available")
            if not available or not available[0]["available"]:
                raise ValueError("CommandLog unavailable")
        findings = await CHECKS[definition.key](context)
        labels = {"check": definition.key}
        if definition.kind == "event":
            seen = set(working.get("seen", []))
            fresh = [f for f in findings if f.dedup_key not in seen and not is_excluded(f, setting) and item_severity(f, definition, setting) in ("WARNING", "CRITICAL")]
            working["total"] = working.get("total", 0) + len(fresh)
            working["seen"] = list(dict.fromkeys(working.get("seen", []) + [f.dedup_key for f in fresh]))[-5000:]
            rows = metric("check_events_total", working["total"], labels, True)
            severity = 0
        else:
            observed, value, _ = summarize(findings, definition, setting)
            confirmed, streak = confirm(working.get("confirmation"), observed, setting.confirm_samples)
            working["confirmation"] = {"severity": confirmed, "observed_severity": observed, "streak": streak}
            severity = RANK[confirmed]
            rows = metric("check_value", value, labels)
            for database in sorted({f.database for f in findings if f.database and not is_excluded(f, setting)}):
                db_severity, db_value, _ = summarize([f for f in findings if f.database == database], definition, setting)
                db_labels = {**labels, "database": database}
                rows += metric("database_check_value", db_value, db_labels)
                rows += metric("database_check_severity", RANK[db_severity], db_labels)
        self.state[key] = working
        try:
            self.save()
        except Exception:
            self.state[key] = previous
            raise
        return rows, severity

    async def instance_cycle(self, instance):
        async with self.semaphore:
            connection = instance.mssql_connection_string

            async def probe():
                await query(connection, "SELECT 1 AS reachable")
                return [], None
            await self.execute(instance, "connection", 0, probe)
            if not self.samples[(instance.name, "connection")]["ok"]:
                for (name, group), entry in self.samples.items():
                    if name == instance.name and group != "connection":
                        entry["ok"] = False
                        self.next_run[(name, group)] = 0
                return
            interval = settings.COLLECTOR_INTERVAL_SECONDS
            # A cycle stops at its time budget so an overloaded instance releases
            # its slot to the rest of the fleet. Groups skipped this cycle are the
            # least recently run, so they go first next time.
            deadline = time.monotonic() + interval
            for group, function, every in sorted(metrics.GROUPS, key=lambda item: self.next_run.get((instance.name, item[0]), 0)):
                if time.monotonic() >= deadline:
                    break

                async def run(function=function):
                    return await function(connection), None
                await self.execute(instance, group, every or interval, run)

    async def check_cycle(self, instance):
        # Checks have their own loop and SQL lane, so they cannot delay the
        # fast metric cycle. Checks in one cycle share a query cache (tempdb
        # space feeds two checks).
        cache = {}
        with query_lane("checks"):
            for definition in self.enabled_checks(instance):
                connection = self.samples[(instance.name, "connection")]
                if not connection["ok"] or time.time() - connection["attempt"] > connection["ttl"]:
                    return
                setting = effective_setting(definition, self.overrides, instance.name)
                await self.execute(instance, "alert." + definition.key, TIER_SECONDS[setting.tier],
                                   lambda d=definition, s=setting: self.check_rows(instance, d, s, cache))

    async def loop(self, instance, function, interval):
        while True:
            start = time.monotonic()
            try:
                await function(instance)
            except Exception as exc:
                # One bad cycle must not end collection for this instance.
                LOG.error("Collection cycle failed instance=%s cycle=%s error=%s", instance.name, function.__name__, type(exc).__name__)
            await asyncio.sleep(max(1, interval - (time.monotonic() - start)))

    async def run(self):
        await asyncio.gather(
            *(self.loop(i, self.instance_cycle, settings.COLLECTOR_INTERVAL_SECONDS) for i in self.instances),
            *(self.loop(i, self.check_cycle, 30) for i in self.instances),
        )
