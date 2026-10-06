"""Check logic against canned DMV rows; no SQL Server is contacted."""

from datetime import datetime, timedelta, timezone

import pytest

from app.modules.alerts.catalog import CATALOG_BY_KEY
from app.modules.alerts.checks import CHECKS
from app.modules.alerts.checks.registry import for_each_database
from app.modules.alerts.evaluation import effective_setting
from app.modules.alerts.models import CheckContext

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


class FakeServer:
    """Answers each query with the next canned response; records the SQL."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.sql = []

    async def __call__(self, sql):
        self.sql.append(sql)
        return self.responses.pop(0)


def ctx(key, server, memory=None, now=NOW):
    setting = effective_setting(CATALOG_BY_KEY[key], {}, "prod")
    return CheckContext("prod", "Driver=x", setting, memory if memory is not None else {}, now, server)


def log_line(when, text, process="spid51"):
    return {"LogDate": when, "LogDateUtc": when.replace(" ", "T"), "ProcessInfo": process, "Text": text}


@pytest.mark.asyncio
async def test_error_log_baselines_then_reads_only_new_lines():
    server = FakeServer([{"ServerNow": "2026-10-05 09:00:00.000"}])
    context = ctx("login_failed", server)
    assert await CHECKS["login_failed"](context) == []
    assert context.memory["since"] == "2026-10-05 09:00:00.000"

    lines = [log_line("2026-10-05 09:01:00.000", f"Login failed for user 'sa'. Reason: Password did not match. [CLIENT: 10.0.0.{i % 2}]")
             for i in range(6)] + [log_line("2026-10-05 09:02:00.000", "Login failed for user 'app'. [CLIENT: 10.0.0.9]")]
    server.responses.append(lines)
    [occurrence] = await CHECKS["login_failed"](context)
    assert "CONVERT(datetime, '2026-10-05 09:00:00.000', 121)" in server.sql[-1] and "N'Login failed'" in server.sql[-1]
    assert occurrence.value == 7 and occurrence.dedup_key == "through:2026-10-05 09:02:00.000"
    assert "sa (6)" in occurrence.detail and "10.0.0.9 (1)" in occurrence.detail
    assert "Password" not in occurrence.detail
    assert context.memory["since"] == "2026-10-05 09:02:00.000"

    # The boundary line is returned again by the inclusive start time and is skipped.
    server.responses.append([lines[-1]])
    assert await CHECKS["login_failed"](context) == []


@pytest.mark.asyncio
async def test_error_log_watermark_is_validated_before_sql():
    context = ctx("backup_failed", FakeServer(), memory={"since": "2026-10-05'; DROP TABLE x;--"})
    with pytest.raises(ValueError):
        await CHECKS["backup_failed"](context)


@pytest.mark.asyncio
async def test_database_errors_classify_and_skip_noise():
    lines = [log_line("2026-10-05 09:01:00.000", "Error: 9002, Severity: 17, State: 2."),
             log_line("2026-10-05 09:01:00.000", "Error: 605, Severity: 21, State: 3.", "spid60"),
             log_line("2026-10-05 09:01:00.000", "Error: 17836, Severity: 20, State: 17.", "Logon"),
             log_line("2026-10-05 09:01:00.000", "Error: 50000, Severity: 16, State: 1.", "spid61")]
    server = FakeServer(lines, [{"MessageId": 9002, "MessageText": "The transaction log for database '%.*ls' is full"}])
    occurrences = await CHECKS["database_errors"](ctx("database_errors", server, {"since": "2026-10-05 09:00:00.000", "seen": []}))
    assert [(o.subject, o.floor) for o in occurrences] == [("Error 9002", "WARNING"), ("Error 605", "CRITICAL")]
    assert "transaction log for database" in occurrences[0].detail
    assert "message_id IN (605, 9002)" in server.sql[-1]


@pytest.mark.asyncio
async def test_io_errors_and_backup_failures():
    io = await CHECKS["io_corruption_errors"](ctx("io_corruption_errors", FakeServer([
        log_line("2026-10-05 09:01:00.000", "Error: 824, Severity: 24, State: 2."),
        log_line("2026-10-05 09:01:00.000", "Error: 825, Severity: 10, State: 2.", "spid70"),
        log_line("2026-10-05 09:01:00.000", "Error: 829, Severity: 21, State: 1.", "spid71")]),
        {"since": "2026-10-05 09:00:00.000", "seen": []}))
    assert [(o.subject, o.floor) for o in io] == [("Error 824", "CRITICAL"), ("Error 825", "WARNING")]
    backups = await CHECKS["backup_failed"](ctx("backup_failed", FakeServer([log_line(
        "2026-10-05 09:01:00.000", "BACKUP failed to complete the command BACKUP LOG Sales. Check the backup application log")]),
        {"since": "2026-10-05 09:00:00.000", "seen": []}))
    assert backups[0].database == "Sales" and "BACKUP LOG failed" in backups[0].detail


@pytest.mark.asyncio
async def test_slow_disk_uses_deltas_and_ignores_resets():
    def files(stall, count):
        return [{"DatabaseName": "Sales", "FileName": "Sales_log", "FileType": "LOG", "StallMs": stall, "IoCount": count},
                {"DatabaseName": "Idle", "FileName": "Idle", "FileType": "ROWS", "StallMs": 10, "IoCount": 10}]
    context = ctx("slow_disk", FakeServer(files(1000, 1000), files(7000, 1200), files(5, 5)))
    assert await CHECKS["slow_disk"](context) == []
    [finding] = await CHECKS["slow_disk"](context)
    assert (finding.subject, finding.value) == ("Sales Sales_log", 30.0)
    assert await CHECKS["slow_disk"](context) == []  # counters restarted


@pytest.mark.asyncio
async def test_job_changes_and_new_databases_after_baseline():
    jobs = FakeServer([{"JobId": "a", "JobName": "Backups", "Enabled": 1}, {"JobId": "b", "JobName": "Old", "Enabled": 1}],
                      [{"JobId": "a", "JobName": "Backups", "Enabled": 0}])
    context = ctx("job_disabled_or_deleted", jobs)
    assert await CHECKS["job_disabled_or_deleted"](context) == []
    changes = await CHECKS["job_disabled_or_deleted"](context)
    assert sorted((o.subject, o.detail) for o in changes) == [("Backups", "job disabled"), ("Old", "job deleted")]

    def db(name, created, backed_up=0):
        return {"DatabaseName": name, "CreateDate": created, "CreateDateUtc": "2026-10-05T12:00:00", "HasFullBackup": backed_up}
    databases = FakeServer([db("Sales", "2020-01-01 00:00:00.000")],
                           [db("Sales", "2020-01-01 00:00:00.000"), db("Staging", "2026-10-05 11:00:00.000")])
    context = ctx("new_database", databases)
    assert await CHECKS["new_database"](context) == []
    [created] = await CHECKS["new_database"](context)
    assert created.subject == "Staging" and "no full backup yet" in created.detail


@pytest.mark.asyncio
async def test_database_growth_normalizes_to_per_day():
    server = FakeServer([{"DatabaseName": "Sales", "DataSizeMB": 1000.0}, {"DatabaseName": "Tiny", "DataSizeMB": 10.0}],
                        [{"DatabaseName": "Sales", "DataSizeMB": 1100.0}, {"DatabaseName": "Tiny", "DataSizeMB": 20.0}])
    context = ctx("database_growth", server)
    assert await CHECKS["database_growth"](context) == []
    context.now = NOW + timedelta(hours=12)
    [finding] = await CHECKS["database_growth"](context)
    assert finding.subject == "Sales" and finding.value == 20.0  # 10% in 12 h; Tiny grew under 100 MB


@pytest.mark.asyncio
async def test_config_and_sysadmin_changes():
    config = FakeServer([{"Name": "max degree of parallelism", "ValueInUse": "0"}],
                        [{"Name": "max degree of parallelism", "ValueInUse": "8"}])
    context = ctx("config_changed", config)
    assert await CHECKS["config_changed"](context) == []
    [change] = await CHECKS["config_changed"](context)
    assert change.detail == "0 → 8"
    admins = FakeServer([{"MemberName": "sa"}], [{"MemberName": "sa"}, {"MemberName": "CORP\\intern"}])
    context = ctx("sysadmin_changed", admins)
    assert await CHECKS["sysadmin_changed"](context) == []
    [added] = await CHECKS["sysadmin_changed"](context)
    assert (added.subject, added.floor) == ("CORP\\intern", "CRITICAL")


@pytest.mark.asyncio
@pytest.mark.parametrize("version,edition,days", [("13.0.7000.1", 3, -83), ("16.0.4135.4", 2, 2290), ("16.0.1000.6", 5, None)])
async def test_version_support(version, edition, days):
    server = FakeServer([{"ProductVersion": version, "ProductLevel": "RTM", "UpdateLevel": None, "EngineEdition": edition}])
    findings = await CHECKS["version_support"](ctx("version_support", server))
    assert [f.value for f in findings] == ([] if days is None else [days])


@pytest.mark.asyncio
async def test_rebuild_failed_baselines_without_reading_history():
    server = FakeServer([{"ID": None, "MaxId": 500}], [
        {"ID": 501, "DatabaseName": "Sales", "ObjectName": "Orders", "IndexName": "pk_order", "CommandType": "ALTER_INDEX",
         "EndTimeUtc": "2026-10-05T11:00:00", "ErrorNumber": 1105, "MaxId": None}, {"ID": None, "MaxId": 502}])
    context = ctx("rebuild_failed", server)
    assert await CHECKS["rebuild_failed"](context) == []
    assert "ID > @last" not in server.sql[0] and context.memory["last_id"] == 500
    [failed] = await CHECKS["rebuild_failed"](context)
    assert "@last = 500" in server.sql[1] and failed.subject == "Sales Orders.pk_order"
    assert context.memory["last_id"] == 502


@pytest.mark.asyncio
async def test_never_backed_up_uses_grace_period_only_for_new_databases():
    rows = [{"DatabaseName": "master", "LastFullBackup": None, "AgeHours": 205956, "AgeOfDatabaseDays": 8581},
            {"DatabaseName": "Staging", "LastFullBackup": None, "AgeHours": 30, "AgeOfDatabaseDays": 1},
            {"DatabaseName": "Sales", "LastFullBackup": "2026-10-04 23:00", "AgeHours": 13, "AgeOfDatabaseDays": 900}]
    master, staging, sales = await CHECKS["full_backup_age"](ctx("full_backup_age", FakeServer(rows)))
    assert (master.value, master.floor, master.detail) == (None, "CRITICAL", "never backed up")
    assert (staging.value, staging.floor, staging.detail) == (30, None, "never backed up")
    assert (sales.value, sales.detail) == (13, "last full 2026-10-04 23:00")


def test_per_database_sql_escapes_quotes():
    sql = for_each_database("SELECT N'x' AS Value", "Value nvarchar(10)")
    assert "N''x''" in sql and "QUOTENAME(@db)" in sql and "HAS_DBACCESS(name) = 1" in sql
