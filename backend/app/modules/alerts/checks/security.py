"""Configuration and security: setting drift, sysadmin, logins, sa, certificates."""

from app.modules.alerts.checks.registry import TO_UTC
from app.modules.alerts.checks.registry import check
from app.modules.alerts.checks.registry import number
from app.modules.alerts.checks.registry import server_now
from app.modules.alerts.checks.registry import as_datetime
from app.modules.alerts.checks.registry import utc
from app.modules.alerts.models import Finding
from app.modules.alerts.models import Occurrence


@check("config_changed")
async def config_changed(ctx):
    rows = await ctx.query("SELECT name AS Name, CAST(value_in_use AS nvarchar(64)) AS ValueInUse FROM sys.configurations")
    current = {row["Name"]: row["ValueInUse"] for row in rows}
    previous = ctx.memory.get("values")
    ctx.memory["values"] = current
    if previous is None:
        return []
    stamp = ctx.now.strftime("%Y%m%d%H%M")
    return [Occurrence(f"{name}:{previous[name]}:{value}:{stamp}", ctx.now, name, detail=f"{previous[name]} → {value}", floor="WARNING")
            for name, value in current.items() if name in previous and previous[name] != value]


@check("max_server_memory_unset")
async def max_server_memory_unset(ctx):
    rows = await ctx.query("""
    SELECT CAST(c.value_in_use AS bigint) AS MaxServerMemoryMB, si.physical_memory_kb / 1024 AS PhysicalMemoryMB
    FROM sys.configurations c
    CROSS JOIN sys.dm_os_sys_info si
    WHERE c.name = N'max server memory (MB)'
    """)
    findings = []
    for row in rows:
        configured, physical = number(row["MaxServerMemoryMB"]) or 0, number(row["PhysicalMemoryMB"]) or 0
        unset = configured >= 2147483647 or configured > physical
        findings.append(Finding("max server memory", detail=f"{configured:,.0f} MB configured, {physical:,.0f} MB physical",
                                floor="WARNING" if unset else None))
    return findings


@check("auto_shrink_close")
async def auto_shrink_close(ctx):
    rows = await ctx.query("""
    SELECT name AS DatabaseName, is_auto_shrink_on AS AutoShrink, is_auto_close_on AS AutoClose
    FROM sys.databases
    WHERE database_id > 4 AND (is_auto_shrink_on = 1 OR is_auto_close_on = 1)
    """)
    return [Finding(row["DatabaseName"], database=row["DatabaseName"], floor="WARNING",
                    detail=" and ".join(name for name, on in (("AUTO_SHRINK", row["AutoShrink"]), ("AUTO_CLOSE", row["AutoClose"])) if on) + " on")
            for row in rows]


@check("page_verify")
async def page_verify(ctx):
    rows = await ctx.query("""
    SELECT name AS DatabaseName, page_verify_option_desc AS PageVerify
    FROM sys.databases
    WHERE database_id <> 2 AND page_verify_option_desc <> N'CHECKSUM'
    """)
    return [Finding(row["DatabaseName"], database=row["DatabaseName"], detail=f"PAGE_VERIFY {row['PageVerify']}", floor="WARNING")
            for row in rows]


@check("sysadmin_changed")
async def sysadmin_changed(ctx):
    rows = await ctx.query("""
    SELECT m.name AS MemberName
    FROM sys.server_role_members rm
    JOIN sys.server_principals r ON r.principal_id = rm.role_principal_id
    JOIN sys.server_principals m ON m.principal_id = rm.member_principal_id
    WHERE r.name = N'sysadmin'
    """)
    current = sorted(row["MemberName"] for row in rows)
    previous = ctx.memory.get("members")
    ctx.memory["members"] = current
    if previous is None:
        return []
    stamp = ctx.now.strftime("%Y%m%d%H%M")
    added = [Occurrence(f"added:{name}:{stamp}", ctx.now, name, detail="added to sysadmin", floor="CRITICAL")
             for name in current if name not in previous]
    removed = [Occurrence(f"removed:{name}:{stamp}", ctx.now, name, detail="removed from sysadmin", floor="WARNING")
               for name in previous if name not in current]
    return added + removed


@check("login_created")
async def login_created(ctx):
    since = ctx.memory.get("since")
    if since is None:
        ctx.memory["since"] = await server_now(ctx)
        return []
    rows = await ctx.query(f"""
    SELECT TOP 100 name AS LoginName, type_desc AS LoginType, CONVERT(varchar(23), create_date, 121) AS CreateDate,
           {TO_UTC.format("create_date")} AS CreateDateUtc
    FROM sys.server_principals
    WHERE type IN ('S', 'U', 'G', 'E', 'X') AND name NOT LIKE N'##%' AND create_date > {as_datetime(since)}
    ORDER BY create_date
    """)
    if rows:
        ctx.memory["since"] = max(row["CreateDate"] for row in rows)
    return [Occurrence(f"{row['LoginName']}:{row['CreateDate']}", utc(row["CreateDateUtc"], ctx.now), row["LoginName"],
                       detail=f"{row['LoginType']} created {row['CreateDate']} (server time)", floor="WARNING") for row in rows]


@check("sa_enabled")
async def sa_enabled(ctx):
    rows = await ctx.query("SELECT name AS LoginName, is_disabled AS IsDisabled FROM sys.server_principals WHERE sid = 0x01")
    return [Finding(row["LoginName"], detail="built-in sa login is enabled" if not row["IsDisabled"] else "disabled",
                    floor=None if row["IsDisabled"] else "WARNING") for row in rows]


@check("certificate_expiry")
async def certificate_expiry(ctx):
    rows = await ctx.query("""
    SELECT c.name AS CertificateName, CONVERT(varchar(10), c.expiry_date, 120) AS ExpiryDate,
           DATEDIFF(DAY, GETUTCDATE(), c.expiry_date) AS DaysLeft,
           CASE WHEN EXISTS (SELECT 1 FROM sys.dm_database_encryption_keys k WHERE k.encryptor_thumbprint = c.thumbprint)
                THEN 1 ELSE 0 END AS UsedByTde
    FROM master.sys.certificates c
    WHERE c.name NOT LIKE N'##%'
    """)
    return [Finding(row["CertificateName"], number(row["DaysLeft"]),
                    detail=f"expires {row['ExpiryDate']}" + ("; protects a TDE database" if row["UsedByTde"] else ""))
            for row in rows]
