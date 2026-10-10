"""Pre-production verification: compare what Data Eyes shows with SQL Server.

Every test reads the truth from SQL Server with its own query (independent of
the collector's SQL) and compares it with the value Prometheus holds, which
is what the UI and alerts display. Run it inside the collector container,
which has the fleet file and reaches both SQL Server and Prometheus:

    docker compose exec collector python -m app.verify
    docker compose exec collector python -m app.verify --instance prod1 --only FAIL,WARN

Read-only: SELECTs, DMVs and DBCC SQLPERF(LOGSPACE). Connection strings are
never printed. Exit code 1 when any test FAILs, so it can gate a release.
"""

import argparse
import asyncio
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

from app.alerts.catalog import CATALOG_BY_KEY, TIER_SECONDS
from app.alerts.evaluation import effective_setting, threshold_severity
from app.config import load_check_settings, load_instances, settings
from app.metrics import GROUPS
from app.sql import query

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")
RANK = {"OK": 0, "UNKNOWN": 1, "WARNING": 2, "CRITICAL": 3}
NAME = {code: name for name, code in RANK.items()}
MB = 1024 ** 2
GB = 1024 ** 3


@dataclass
class Result:
    instance: str
    area: str
    test: str
    subject: str
    sql: str
    shown: str
    status: str  # PASS, FAIL, WARN (review by hand), SKIP
    note: str = ""


def prom(promql: str) -> List[tuple]:
    url = f"{PROMETHEUS_URL}/api/v1/query?query={urllib.parse.quote(promql)}"
    with urllib.request.urlopen(url, timeout=15) as response:
        data = json.load(response)["data"]["result"]
    return [(sample["metric"], float(sample["value"][1])) for sample in data]


def prom_map(promql: str, label: str) -> Dict[str, float]:
    return {labels.get(label, ""): value for labels, value in prom(promql)}


def prom_one(promql: str) -> Optional[float]:
    rows = prom(promql)
    return rows[0][1] if rows else None


def close(truth: Optional[float], shown: Optional[float], abs_tol: float, rel_tol: float = 0.0) -> bool:
    if truth is None or shown is None:
        return truth is None and shown is None
    return abs(truth - shown) <= max(abs_tol, abs(truth) * rel_tol)


def fmt(value, unit: str = "") -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        value = round(value, 1)
    return f"{value}{unit}"


class Verifier:
    def __init__(self, instance, overrides):
        self.instance = instance
        self.name = instance.name
        self.sel = f'sql_instance="{instance.name}"'
        self.overrides = overrides
        self.results: List[Result] = []

    async def sql(self, text: str):
        return await query(self.instance.mssql_connection_string, text)

    def add(self, area, test, subject, sql, shown, ok, note="", soft=False):
        status = "PASS" if ok else ("WARN" if soft else "FAIL")
        self.results.append(Result(self.name, area, test, subject, str(sql), str(shown), status, note))

    def skip(self, area, test, note):
        self.results.append(Result(self.name, area, test, "", "", "", "SKIP", note))

    def setting(self, key):
        return effective_setting(CATALOG_BY_KEY[key], self.overrides, self.name)

    def check_severity(self, key) -> Optional[int]:
        value = prom_one(f'data_eyes_health_severity{{{self.sel},category="alert.{key}"}}')
        return None if value is None else int(value)

    def db_values(self, key) -> Dict[str, float]:
        return prom_map(f'data_eyes_database_check_value{{{self.sel},check="{key}"}}', "database")

    def expected(self, key, value, floor="OK") -> str:
        setting = self.setting(key)
        by_value = threshold_severity(value, setting.warning, setting.critical, CATALOG_BY_KEY[key].direction)
        return max(by_value, floor, key=RANK.get)

    def compare_severity(self, area, key, expected: str, note=""):
        shown = self.check_severity(key)
        if shown is None:
            if not self.setting(key).enabled:
                return self.skip(area, f"{key} severity", "check disabled in checks.yaml")
            return self.add(area, f"{key} severity", "instance", expected, "no series", False, "check never reported")
        lag = f"confirm_samples={self.setting(key).confirm_samples}, tier={self.setting(key).tier}; rerun if a threshold was just crossed"
        self.add(area, f"{key} severity", "instance", expected, NAME[shown], NAME[shown] == expected, note or lag)

    # ---- 1. Pipeline -------------------------------------------------------
    async def pipeline(self):
        area = "1 Pipeline"
        try:
            await self.sql("SELECT 1 AS ok")
            reachable = 1
        except Exception as exc:
            reachable = 0
            self.add(area, "SQL connection", "login", "connects", type(exc).__name__, False, "other tests skipped")
        shown = prom_one(f"data_eyes_sqlserver_reachable{{{self.sel}}}")
        self.add(area, "reachable flag", "instance", reachable, fmt(shown), shown == reachable)
        if not reachable:
            return False

        failing = prom(f"data_eyes_collection_success{{{self.sel}}} == 0")
        names = ", ".join(sorted(labels["collector"] for labels, _ in failing))
        self.add(area, "every collector succeeding", "instance", "0 failing", f"{len(failing)} failing", not failing, names)

        now = time.time()
        stale = []
        intervals = {group: every or settings.COLLECTOR_INTERVAL_SECONDS for group, _, every in GROUPS}
        for labels, last in prom(f"data_eyes_collection_last_success_timestamp_seconds{{{self.sel}}}"):
            collector = labels["collector"]
            key = collector.removeprefix("alert.")
            if collector.startswith("alert.") and key in CATALOG_BY_KEY:
                interval = TIER_SECONDS[self.setting(key).tier]
            else:
                interval = intervals.get(collector, settings.COLLECTOR_INTERVAL_SECONDS)
            if now - last > interval * 2 + 120:
                stale.append(f"{collector} ({(now - last) / 60:.0f} min)")
        self.add(area, "results fresh (< 2 intervals)", "instance", "0 stale", f"{len(stale)} stale", not stale, ", ".join(stale))

        overall = prom_one(f"data_eyes_overall_severity{{{self.sel}}}")
        worst = prom_one(f"max(data_eyes_health_severity{{{self.sel}}})")
        self.add(area, "overall = worst check", "instance", fmt(worst), fmt(overall), overall == worst)
        return True

    # ---- 2. Server facts ---------------------------------------------------
    async def server(self):
        area = "2 Server"
        [row] = await self.sql("""
        SELECT CAST(SERVERPROPERTY('ProductVersion') AS nvarchar(128)) AS version,
               CAST(SERVERPROPERTY('Edition') AS nvarchar(128)) AS edition,
               si.cpu_count AS cores, si.physical_memory_kb AS physical_kb, si.max_workers_count AS max_workers,
               sm.available_physical_memory_kb AS available_kb, pm.physical_memory_in_use_kb AS sql_kb,
               (SELECT cntr_value FROM sys.dm_os_performance_counters
                WHERE counter_name = 'Page life expectancy' AND object_name LIKE '%Buffer Manager%') AS ple
        FROM sys.dm_os_sys_info si CROSS JOIN sys.dm_os_sys_memory sm CROSS JOIN sys.dm_os_process_memory pm
        """)
        info = prom(f"data_eyes_server_info{{{self.sel}}}")
        labels = info[0][0] if info else {}
        self.add(area, "version", "server", row["version"], labels.get("version"), row["version"] == labels.get("version"))
        self.add(area, "edition", "server", row["edition"], labels.get("edition"), row["edition"] == labels.get("edition"))
        cores = prom_one(f"data_eyes_server_cores{{{self.sel}}}")
        self.add(area, "CPU cores", "server", row["cores"], fmt(cores), cores == row["cores"])
        physical = row["physical_kb"] * 1024
        shown = prom_one(f"data_eyes_server_memory_bytes{{{self.sel}}}")
        self.add(area, "physical memory", "server", fmt(physical / MB, " MB"), fmt(shown and shown / MB, " MB"), close(physical, shown, MB))
        workers = prom_one(f"data_eyes_workers_max{{{self.sel}}}")
        self.add(area, "max worker threads", "server", row["max_workers"], fmt(workers), workers == row["max_workers"])
        available = row["available_kb"] * 1024
        shown = prom_one(f"data_eyes_available_memory_bytes{{{self.sel}}}")
        self.add(area, "available memory", "server", fmt(available / MB, " MB"), fmt(shown and shown / MB, " MB"),
                 close(available, shown, 256 * MB, 0.2), "±256 MB / 20%: moves between samples")
        sql_mem = row["sql_kb"] * 1024
        shown = prom_one(f"data_eyes_sql_memory_bytes{{{self.sel}}}")
        self.add(area, "SQL Server memory in use", "server", fmt(sql_mem / MB, " MB"), fmt(shown and shown / MB, " MB"),
                 close(sql_mem, shown, 256 * MB, 0.2))
        self.add(area, "SQL memory <= physical memory", "server", fmt(physical / MB, " MB"), fmt(sql_mem / MB, " MB"),
                 sql_mem <= physical, "physical_memory_in_use_kb above RAM (seen on SQL Server on Linux): the instance card shows SQL using more than the server has", soft=True)
        ple = prom_one(f"data_eyes_page_life_expectancy_seconds{{{self.sel}}}")
        self.add(area, "page life expectancy", "server", fmt(row["ple"], " s"), fmt(ple, " s"), close(row["ple"], ple, 600, 0.5),
                 "±600 s / 50%: grows one per second")

        volumes = await self.sql("""
        SELECT DISTINCT ISNULL(vs.volume_mount_point, '') AS drive, vs.available_bytes AS free
        FROM sys.master_files mf CROSS APPLY sys.dm_os_volume_stats(mf.database_id, mf.file_id) vs""")
        shown_free = prom_map(f"data_eyes_volume_free_bytes{{{self.sel}}}", "drive")
        for volume in volumes:
            shown = shown_free.get(volume["drive"])
            self.add(area, "volume free space", volume["drive"] or "(volume)", fmt(volume["free"] / GB, " GB"),
                     fmt(shown and shown / GB, " GB"), close(volume["free"], shown, 2 * GB))

    # ---- 3. Databases ------------------------------------------------------
    async def databases(self):
        area = "3 Databases"
        rows = await self.sql("""
        SELECT d.name, d.state, CAST(DATABASEPROPERTYEX(d.name, 'Updateability') AS nvarchar(60)) AS updateability,
               (SELECT SUM(CAST(size AS bigint)) * 8192 FROM sys.master_files m WHERE m.database_id = d.database_id) AS size_bytes,
               ars.role_desc AS role
        FROM sys.databases d
        LEFT JOIN sys.dm_hadr_availability_replica_states ars ON ars.replica_id = d.replica_id AND ars.is_local = 1""")
        states = prom_map(f"data_eyes_database_state{{{self.sel}}}", "database")
        sizes = prom_map(f"data_eyes_database_size_bytes{{{self.sel}}}", "database")
        info = {labels["database"]: labels for labels, _ in prom(f"data_eyes_database_info{{{self.sel}}}")}
        truth = {row["name"] for row in rows}
        self.add(area, "database list", "instance", len(truth), len(states), truth == set(states),
                 "missing: " + ", ".join(sorted(truth - set(states))) + "; extra: " + ", ".join(sorted(set(states) - truth)))
        for row in rows:
            db = row["name"]
            self.add(area, "state", db, row["state"], fmt(states.get(db)), states.get(db) == row["state"])
            self.add(area, "size", db, fmt(row["size_bytes"] / MB, " MB"), fmt(sizes.get(db) and sizes[db] / MB, " MB"),
                     close(row["size_bytes"], sizes.get(db), 64 * MB, 0.05), "refreshed every 5 min")
            labels = info.get(db, {})
            self.add(area, "read/write mode", db, row["updateability"], labels.get("updateability"),
                     (row["updateability"] or "") == labels.get("updateability", ""))
            self.add(area, "AG replica role", db, row["role"] or "—", labels.get("replica_role") or "—",
                     (row["role"] or "") == labels.get("replica_role", ""))

    # ---- 4. Alert checks ---------------------------------------------------
    async def alerts(self):
        area = "4 Alerts"
        [row] = await self.sql("""
        SELECT (SELECT CAST(value_in_use AS bigint) FROM sys.configurations WHERE name = 'max server memory (MB)') AS max_mb,
               (SELECT physical_memory_kb / 1024 FROM sys.dm_os_sys_info) AS physical_mb,
               (SELECT is_disabled FROM sys.server_principals WHERE sid = 0x01) AS sa_disabled,
               (SELECT available_physical_memory_kb / 1024 FROM sys.dm_os_sys_memory) AS available_mb,
               (SELECT COUNT(*) FROM sys.databases WHERE state_desc <> 'ONLINE') AS not_online,
               (SELECT COUNT(*) FROM msdb.dbo.suspect_pages WHERE event_type IN (1, 2, 3)) AS suspect_pages
        """)
        unset = row["max_mb"] >= 2147483647 or row["max_mb"] > row["physical_mb"]
        self.compare_severity(area, "max_server_memory_unset", "WARNING" if unset else "OK", f"max server memory {row['max_mb']:,} MB")
        self.compare_severity(area, "sa_enabled", "OK" if row["sa_disabled"] else "WARNING")
        self.compare_severity(area, "database_status", "OK" if not row["not_online"] else "WARNING",
                              f"{row['not_online']} database(s) not ONLINE; SUSPECT/RECOVERY_PENDING would be CRITICAL")
        self.compare_severity(area, "page_corruption", self.expected("page_corruption", row["suspect_pages"] or None),
                              f"{row['suspect_pages']} unrepaired suspect page(s)")
        self.compare_severity(area, "memory_available", self.expected("memory_available", row["available_mb"]))
        shown = prom_one(f'data_eyes_check_value{{{self.sel},check="memory_available"}}')
        self.add(area, "memory_available value", "instance", fmt(row["available_mb"], " MB"), fmt(shown, " MB"),
                 close(row["available_mb"], shown, 256, 0.2))

        agents = await self.sql("""SELECT status_desc, startup_type_desc FROM sys.dm_server_services
                                   WHERE servicename LIKE N'SQL Server Agent%'""")
        stopped = any(a["status_desc"] != "Running" and a["startup_type_desc"] != "Disabled" for a in agents)
        self.compare_severity(area, "agent_service_stopped", "CRITICAL" if stopped else "OK")

        # CHECKDB: 1900-01-01 means never checked.
        checkdb = await self.sql("""
        SELECT d.name, CONVERT(char(4), lg.last_good, 120) AS last_year, DATEDIFF(DAY, lg.last_good, GETDATE()) AS days,
               DATEDIFF(DAY, d.create_date, GETDATE()) AS created_days
        FROM sys.databases d
        CROSS APPLY (SELECT CAST(DATABASEPROPERTYEX(d.name, 'LastGoodCheckDbTime') AS datetime) AS last_good) lg
        WHERE d.database_id <> 2 AND d.state_desc = 'ONLINE' AND d.source_database_id IS NULL""")
        shown_values = self.db_values("checkdb_age")
        shown_sev = prom_map(f'data_eyes_database_check_severity{{{self.sel},check="checkdb_age"}}', "database")
        warning = self.setting("checkdb_age").warning
        worst = "OK"
        for item in checkdb:
            db, year = item["name"], item["last_year"]
            if year is None:
                expected, days = "UNKNOWN", None
            elif year == "1900":
                expected = "WARNING" if warning is None or item["created_days"] >= warning else "OK"
                days = None
            else:
                days = item["days"]
                expected = self.expected("checkdb_age", days)
            worst = max(worst, expected, key=RANK.get)
            got = NAME.get(int(shown_sev[db])) if db in shown_sev else None
            self.add(area, "checkdb_age per database", db, f"{expected} ({'never' if days is None else fmt(days, ' d')})",
                     f"{got} ({fmt(shown_values.get(db), ' d')})",
                     got == expected and close(days, shown_values.get(db), 1), "checked daily: value can trail by a day")
        self.compare_severity(area, "checkdb_age", worst)

        # Backups, per database.
        backups = await self.sql("""
        SELECT d.name, d.recovery_model_desc AS recovery, d.database_id AS id,
               DATEDIFF(MINUTE, MAX(CASE WHEN b.type = 'D' THEN b.backup_finish_date END), GETDATE()) / 60.0 AS full_hours,
               DATEDIFF(MINUTE, MAX(CASE WHEN b.type = 'L' THEN b.backup_finish_date END), GETDATE()) AS log_minutes
        FROM sys.databases d LEFT JOIN msdb.dbo.backupset b ON b.database_name = d.name
        WHERE d.database_id <> 2 AND d.state_desc = 'ONLINE' GROUP BY d.name, d.recovery_model_desc, d.database_id""")
        full, log = self.db_values("full_backup_age"), self.db_values("log_backup_age")
        for item in backups:
            db = item["name"]
            if item["full_hours"] is not None:
                truth = float(item["full_hours"])
                self.add(area, "full_backup_age", db, fmt(truth, " h"), fmt(full.get(db), " h"), close(truth, full.get(db), 2),
                         "checked hourly: ±2 h")
            # The check covers user databases only (system databases are skipped by design).
            if item["id"] > 4 and item["recovery"] != "SIMPLE" and item["log_minutes"] is not None:
                self.add(area, "log_backup_age", db, fmt(item["log_minutes"], " min"), fmt(log.get(db), " min"),
                         close(item["log_minutes"], log.get(db), 12), "checked every 5 min: ±12 min")

        # Transaction log usage. AG secondaries report no log usage for their databases.
        logs = await self.sql("""
        SET NOCOUNT ON;
        CREATE TABLE #log (db sysname, size_mb float, used_pct float, status int);
        INSERT INTO #log EXEC (N'DBCC SQLPERF(LOGSPACE) WITH NO_INFOMSGS');
        SELECT l.db, l.size_mb, l.used_pct FROM #log l JOIN sys.databases d ON d.name = l.db
        WHERE d.database_id <> 2 AND d.state_desc = 'ONLINE'""")
        shown_log = self.db_values("transaction_log_health")
        for item in logs:
            db, scored = item["db"], item["size_mb"] >= 64
            truth = round(item["used_pct"], 1) if scored else None
            self.add(area, "transaction_log_health", db, fmt(truth, "%") + ("" if scored else " (under 64 MB)"),
                     fmt(shown_log.get(db), "%"), close(truth, shown_log.get(db), 15), "±15 points: log usage moves fast")

        # Storage and tempdb.
        [space] = await self.sql("""
        SELECT (SELECT MIN(vs.available_bytes) / 1073741824.0 FROM sys.master_files mf
                CROSS APPLY sys.dm_os_volume_stats(mf.database_id, mf.file_id) vs) AS min_free_gb,
               (SELECT 100.0 * SUM(allocated_extent_page_count) / NULLIF(SUM(total_page_count), 0)
                FROM tempdb.sys.dm_db_file_space_usage) AS tempdb_pct""")
        for key, truth, tol, unit in [("disk_space", space["min_free_gb"], 2, " GB"), ("tempdb_data_utilization", space["tempdb_pct"], 5, "%")]:
            truth = float(truth) if truth is not None else None
            shown = prom_one(f'data_eyes_check_value{{{self.sel},check="{key}"}}')
            self.add(area, f"{key} value", "instance", fmt(truth, unit), fmt(shown, unit), close(truth, shown, tol))
            self.compare_severity(area, key, self.expected(key, truth))

        certs = await self.sql("""SELECT MIN(DATEDIFF(DAY, GETDATE(), expiry_date)) AS days, COUNT(*) AS n
                                  FROM master.sys.certificates WHERE name NOT LIKE '##%'""")
        days = certs[0]["days"] if certs and certs[0]["n"] else None
        shown = prom_one(f'data_eyes_check_value{{{self.sel},check="certificate_expiry"}}')
        self.add(area, "certificate_expiry value", "instance", fmt(days, " d"), fmt(shown, " d"), close(days, shown, 1),
                 "no certificates means no value")

        # Always On: a replica that is not HEALTHY must not show OK.
        ag = await self.sql("""SELECT COUNT(*) AS n,
                                      SUM(CASE WHEN synchronization_health_desc <> 'HEALTHY' THEN 1 ELSE 0 END) AS unhealthy
                               FROM sys.dm_hadr_database_replica_states""")
        if ag[0]["n"]:
            shown = self.check_severity("ag_health")
            healthy = not ag[0]["unhealthy"]
            self.add(area, "ag_health matches replica health", "instance", "OK" if healthy else "WARNING or worse",
                     NAME.get(shown), (shown == 0) == healthy)
        else:
            self.skip(area, "ag_health", "no availability group databases")

        # Ola Hallengren CommandLog checks need the table to be visible.
        [cl] = await self.sql("SELECT CASE WHEN OBJECT_ID(N'master.dbo.CommandLog') IS NULL THEN 0 ELSE 1 END AS visible")
        for key in ("database_corruption", "rebuild_failed"):
            if not self.setting(key).enabled:
                self.skip(area, key, "disabled in checks.yaml")
                continue
            ok = prom_one(f'data_eyes_collection_success{{{self.sel},collector="alert.{key}"}}')
            self.add(area, f"{key} runs", "instance", "CommandLog visible" if cl["visible"] else "CommandLog missing",
                     "success" if ok == 1 else "failing", bool(cl["visible"]) and ok == 1,
                     "install Ola in master and grant SELECT, or disable the check")

    # ---- 5. Signals that need a human look ---------------------------------
    async def review(self):
        area = "5 Review"
        top = prom(f"topk(5, sum by (category) (rate(data_eyes_wait_seconds_total{{{self.sel}}}[5m])))")
        total = sum(value for _, value in top)
        detail = ", ".join(f"{labels.get('category')}={value:.2f}" for labels, value in top if value >= 0.05)
        self.add(area, "wait rate plausible", "instance", "< 1 s/s on an idle server", f"{total:.2f} s/s", total < 1, detail, soft=True)

    async def run(self):
        if await self.pipeline():
            for step in (self.server, self.databases, self.alerts, self.review):
                try:
                    await step()
                except Exception as exc:
                    self.add(step.__name__, "test step", "instance", "ran", type(exc).__name__, False, str(exc)[:200])
        return self.results


def print_table(results: List[Result], only: Optional[set]):
    rows = [r for r in results if not only or r.status in only]
    widths = [8, 11, 34, 18, 26, 26, 5]
    header = ["INSTANCE", "AREA", "TEST", "SUBJECT", "SQL SERVER", "DATA EYES", "OK"]
    print("  ".join(h.ljust(w) for h, w in zip(header, widths)))
    for r in rows:
        cells = [r.instance, r.area, r.test, r.subject, r.sql, r.shown, r.status]
        print("  ".join(str(c)[:w].ljust(w) for c, w in zip(cells, widths)) + (f"  {r.note}" if r.status != "PASS" and r.note else ""))
    counts = {s: sum(r.status == s for r in results) for s in ("PASS", "FAIL", "WARN", "SKIP")}
    print("\n" + "  ".join(f"{k} {v}" for k, v in counts.items()))


async def main():
    parser = argparse.ArgumentParser(description="Compare Data Eyes values with SQL Server (read-only).")
    parser.add_argument("--instance", action="append", help="limit to these instances (repeatable)")
    parser.add_argument("--only", help="show only these statuses, e.g. FAIL,WARN")
    parser.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = parser.parse_args()

    try:
        prom("up")
    except Exception as exc:
        sys.exit(f"Prometheus not reachable at {PROMETHEUS_URL}: {type(exc).__name__}")
    overrides = load_check_settings()
    instances = [i for i in load_instances() if not args.instance or i.name in args.instance]
    results: List[Result] = []
    scrape = prom_one('min(up{job="data-eyes"})')
    results.append(Result("fleet", "1 Pipeline", "Prometheus scrapes the collector", "job data-eyes", "1", fmt(scrape),
                          "PASS" if scrape == 1 else "FAIL"))
    configured = {i.name for i in load_instances()}
    exported = {labels["sql_instance"] for labels, _ in prom("data_eyes_instance_info")}
    results.append(Result("fleet", "1 Pipeline", "instances.yaml = instances shown", "fleet", len(configured), len(exported),
                          "PASS" if configured == exported else "FAIL", f"missing {sorted(configured - exported)}"))
    for instance in instances:
        results += await Verifier(instance, overrides).run()

    if args.json:
        print(json.dumps([asdict(r) for r in results], indent=1, default=str))
    else:
        print_table(results, set(args.only.split(",")) if args.only else None)
    sys.exit(1 if any(r.status == "FAIL" for r in results) else 0)


if __name__ == "__main__":
    asyncio.run(main())
