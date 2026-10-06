"""Resources implementation."""

from typing import Any, Dict, List, Optional
from app.modules.monitoring.diagnostics.health import _SQL_BUFFER_GAUGES
from app.modules.monitoring.diagnostics.health import _SQL_CPU_HISTORY
from app.modules.monitoring.diagnostics.health import _SQL_ERROR_COUNTERS
from app.modules.monitoring.diagnostics.health import _SQL_FILE_IO_STATS
from app.modules.monitoring.diagnostics.health import _SQL_MEMORY_STATS
from app.modules.monitoring.diagnostics.health import _SQL_RATE_COUNTERS
from app.modules.monitoring.diagnostics.health import _SQL_SERVER_OVERVIEW
from app.modules.monitoring.diagnostics.health import _SQL_WORKER_STATS
from app.modules.monitoring.diagnostics.common import _query


async def file_io_stats(connection_string: str) -> List[Dict[str, Any]]:
    """Cumulative-since-restart IO stall time, bytes transferred, and IO
    count per data/log file, with its drive (volume_mount_point) — same
    dm_os_volume_stats join _sql_db_space() uses for free space. Cumulative,
    so app/modules/monitoring/collector.py diffs this between cycles (same delta technique as
    wait_stats -> wait_category_snapshot) rather than persisting it as-is."""
    return await _query(connection_string, _SQL_FILE_IO_STATS)


async def worker_stats(connection_string: str) -> Dict[str, Any]:
    """Worker thread pool pressure — max configured, currently created, and
    idle (created but not doing work right now). Point-in-time gauges, same
    shape as resource_utilization's buffer-cache gauges."""
    rows = await _query(connection_string, _SQL_WORKER_STATS)
    return rows[0] if rows else {}


async def memory_stats(connection_string: str) -> Dict[str, Any]:
    """SQL Server's own memory footprint (physical_memory_in_use), its
    configured target, and OS-level free physical memory — point-in-time
    gauges, not cumulative counters."""
    rows = await _query(connection_string, _SQL_MEMORY_STATS)
    return rows[0] if rows else {}


async def error_rate_stats(connection_string: str) -> Optional[float]:
    """Cumulative-since-restart count of meaningful SQL Server errors —
    excludes the benign 'Info Errors' instance, same exclusion-list
    philosophy as _BENIGN_WAIT_TYPES_SQL's benign wait types. Only
    meaningful as a rate: app/modules/monitoring/collector.py diffs this between cycles, same
    delta technique as resource_utilization's disk/batch counters, and
    derives a severity from the delta (0 = OK, some errors = WARNING/CRITICAL)."""
    rows = await _query(connection_string, _SQL_ERROR_COUNTERS)
    if not rows:
        return None
    value = rows[0].get("ErrorCount")
    return float(value) if value is not None else None


async def server_overview(connection_string: str) -> Dict[str, Any]:
    """Static-ish server facts (version, host, cores, total memory/disk) —
    powers the Fleet Status row-expand and Admin's instance table."""
    rows = await _query(connection_string, _SQL_SERVER_OVERVIEW)
    return rows[0] if rows else {}


async def resource_utilization(connection_string: str) -> Dict[str, Any]:
    """Current resource gauges for the Resources tab.

    Buffer cache hit % and Page Life Expectancy are true point-in-time
    gauges — no history needed to know "now". CPU % history comes free from
    SQL Server's own scheduler-monitor ring buffer (~4h at ~1min resolution,
    no collection needed on our side). Disk read bytes and batch requests
    are *cumulative* counters since instance start — meaningless as a single
    number, so this returns the raw totals for app/modules/monitoring/collector.py to diff
    between cycles into an actual rate; a live "current" MB/s or requests/sec
    figure only exists once at least two collector samples have landed.
    """
    gauges_rows = await _query(connection_string, _SQL_BUFFER_GAUGES)
    gauges = gauges_rows[0] if gauges_rows else {}
    buffer_hit_raw = gauges.get("BufferHitRaw")
    buffer_hit_base = gauges.get("BufferHitBase")
    buffer_cache_hit_pct = (
        round(100.0 * buffer_hit_raw / buffer_hit_base, 2)
        if buffer_hit_raw is not None and buffer_hit_base
        else None
    )

    cpu_rows = await _query(connection_string, _SQL_CPU_HISTORY)
    cpu_history = list(reversed(cpu_rows))  # oldest first, for charting
    latest_cpu = cpu_rows[0] if cpu_rows else {}
    system_idle_pct = latest_cpu.get("SystemIdlePct")
    # SQL Server's own share of CPU vs. the OS total (SQL + every other
    # process) — the ring buffer's SystemIdle is OS-wide idle %, so
    # 100 - SystemIdle is total OS utilization, of which ProcessUtilization
    # is SQL Server's slice.
    os_cpu_pct = (100 - system_idle_pct) if system_idle_pct is not None else None

    rate_rows = await _query(connection_string, _SQL_RATE_COUNTERS)
    raw_counters = rate_rows[0] if rate_rows else {}

    return {
        "buffer_cache_hit_pct": buffer_cache_hit_pct,
        "page_life_expectancy_seconds": gauges.get("PageLifeExpectancySeconds"),
        "cpu_history": cpu_history,
        "sql_cpu_pct": latest_cpu.get("CpuPct"),
        "os_cpu_pct": os_cpu_pct,
        "disk_read_bytes_total": raw_counters.get("DiskReadBytesTotal"),
        "batch_requests_total": raw_counters.get("BatchRequestsTotal"),
    }
