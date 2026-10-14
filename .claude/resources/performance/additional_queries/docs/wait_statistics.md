# SQL Server Wait Statistics Analysis

## Overview
This query analyzes SQL Server wait statistics to identify performance bottlenecks by examining what types of waits are consuming the most time since the SQL Server instance started or statistics were cleared.

## Purpose
Analyze SQL Server wait statistics to identify performance bottlenecks

## Query Documentation
```sql
SELECT	
    wait_type AS Wait_Type, 
    wait_time_ms / 1000.0 AS Wait_Time_Seconds,
    waiting_tasks_count AS Waiting_Tasks_Count,
    -- CAST((wait_time_ms / 1000.0)/waiting_tasks_count AS decimal(10,4)) AS AVG_Waiting_Tasks_Count,
    wait_time_ms * 100.0 / SUM(wait_time_ms) OVER() AS Percentage_WaitTime
    --,waiting_tasks_count * 100.0 / SUM(waiting_tasks_count) OVER() AS Percentage_Count
FROM sys.dm_os_wait_stats
WHERE wait_type NOT IN 
(
    -- Exclude benign/system wait types that don't indicate performance issues
    N'BROKER_EVENTHANDLER', N'BROKER_RECEIVE_WAITFOR', N'BROKER_TASK_STOP',
    N'BROKER_TO_FLUSH', N'BROKER_TRANSMITTER', N'CHECKPOINT_QUEUE',
    N'CHKPT', N'CLR_AUTO_EVENT', N'CLR_MANUAL_EVENT', N'CLR_SEMAPHORE',
    N'DBMIRROR_DBM_EVENT', N'DBMIRROR_DBM_MUTEX', N'DBMIRROR_EVENTS_QUEUE',
    N'DBMIRROR_WORKER_QUEUE', N'DBMIRRORING_CMD', N'DIRTY_PAGE_POLL',
    N'DISPATCHER_QUEUE_SEMAPHORE', N'EXECSYNC', N'FSAGENT',
    N'FT_IFTS_SCHEDULER_IDLE_WAIT', N'FT_IFTSHC_MUTEX',
    N'HADR_CLUSAPI_CALL', N'HADR_FILESTREAM_IOMGR_IOCOMPLETION',
    N'HADR_LOGCAPTURE_WAIT', N'HADR_NOTIFICATION_DEQUEUE', N'HADR_TIMER_TASK',
    N'HADR_WORK_QUEUE', N'LAZYWRITER_SLEEP', N'LOGMGR_QUEUE',
    N'MEMORY_ALLOCATION_EXT', N'ONDEMAND_TASK_QUEUE',
    N'PREEMPTIVE_HADR_LEASE_MECHANISM', N'PREEMPTIVE_OS_AUTHENTICATIONOPS',
    N'PREEMPTIVE_OS_AUTHORIZATIONOPS', N'PREEMPTIVE_OS_COMOPS',
    N'PREEMPTIVE_OS_CREATEFILE', N'PREEMPTIVE_OS_CRYPTOPS',
    N'PREEMPTIVE_OS_DEVICEOPS', N'PREEMPTIVE_OS_FILEOPS',
    N'PREEMPTIVE_OS_GENERICOPS', N'PREEMPTIVE_OS_LIBRARYOPS',
    N'PREEMPTIVE_OS_PIPEOPS', N'PREEMPTIVE_OS_QUERYREGISTRY',
    N'PREEMPTIVE_OS_VERIFYTRUST', N'PREEMPTIVE_OS_WAITFORSINGLEOBJECT',
    N'PREEMPTIVE_OS_WRITEFILEGATHER', N'PREEMPTIVE_SP_SERVER_DIAGNOSTICS',
    N'PREEMPTIVE_XE_GETTARGETSTATE', N'PWAIT_ALL_COMPONENTS_INITIALIZED',
    N'PWAIT_DIRECTLOGCONSUMER_GETNEXT', N'QDS_ASYNC_QUEUE',
    N'QDS_CLEANUP_STALE_QUERIES_TASK_MAIN_LOOP_SLEEP',
    N'QDS_PERSIST_TASK_MAIN_LOOP_SLEEP', N'QDS_SHUTDOWN_QUEUE',
    N'REDO_THREAD_PENDING_WORK', N'REQUEST_FOR_DEADLOCK_SEARCH',
    N'RESOURCE_QUEUE', N'SERVER_IDLE_CHECK', N'SLEEP_BPOOL_FLUSH',
    N'SLEEP_DBSTARTUP', N'SLEEP_DCOMSTARTUP', N'SLEEP_MASTERDBREADY',
    N'SLEEP_MASTERMDREADY', N'SLEEP_MASTERUPGRADED', N'SLEEP_MSDBSTARTUP',
    N'SLEEP_SYSTEMTASK', N'SLEEP_TASK', N'SP_SERVER_DIAGNOSTICS_SLEEP',
    N'SQLTRACE_BUFFER_FLUSH', N'SQLTRACE_INCREMENTAL_FLUSH_SLEEP',
    N'SQLTRACE_WAIT_ENTRIES', N'UCS_SESSION_REGISTRATION',
    N'WAIT_FOR_RESULTS', N'WAIT_XTP_CKPT_CLOSE', N'WAIT_XTP_HOST_WAIT',
    N'WAIT_XTP_OFFLINE_CKPT_NEW_LOG', N'WAIT_XTP_RECOVERY',
    N'WAITFOR', N'WAITFOR_TASKSHUTDOWN', N'XE_TIMER_EVENT',
    N'XE_DISPATCHER_WAIT'
) 
AND wait_time_ms >= 1  -- Only include waits with measurable time
ORDER BY Wait_Time_Seconds DESC
-- ORDER BY Waiting_Tasks_Count DESC
```

## Output Columns
| Column Name | Description |
|-------------|-------------|
| `Wait_Type` | Type of wait that occurred |
| `Wait_Time_Seconds` | Total time spent waiting (in seconds) |
| `Waiting_Tasks_Count` | Number of times this wait type occurred |
| `Percentage_WaitTime` | Percentage of total wait time consumed by this wait type |

## Common Wait Types and Their Meanings

### Critical Performance Wait Types

| Wait Type | Indicates | Potential Solutions |
|-----------|-----------|---------------------|
| **CXPACKET** | Parallel query execution | Check for statistics issues, adjust MAXDOP |
| **PAGEIOLATCH_** | Disk I/O bottlenecks | Add memory, optimize queries, faster storage |
| **LCK_** | Blocking and locking issues | Optimize transactions, reduce lock times |
| **SOS_SCHEDULER_YIELD** | CPU pressure | Optimize queries, add CPU capacity |
| **WRITELOG** | Transaction log bottlenecks | Faster storage, optimize commits |

### Key Wait Categories
#### I/O Related Waits
- **PAGEIOLATCH_SH**: Waiting for data page reads
- **PAGEIOLATCH_EX**: Waiting for data page writes
- **WRITELOG**: Transaction log write delays
- **ASYNC_IO_COMPLETION**: Async I/O operations

#### CPU Related Waits
- **SOS_SCHEDULER_YIELD**: Thread yielding CPU
- **CXPACKET**: Parallel query coordination
- **CMEMTHREAD**: Memory object allocation

#### Lock Related Waits
- **LCK_M_IS**, **LCK_M_IU**, **LCK_M_IX**: Intent shared/update/exclusive locks
- **LCK_M_S**, **LCK_M_U**, **LCK_M_X**: Shared/update/exclusive locks
- **LCK_M_SCH_S**, **LCK_M_SCH_M**: Schema stability/modification locks

#### Memory Related Waits
- **RESOURCE_SEMAPHORE**: Memory grants
- **PAGELATCH_**: Buffer latch contention

## Usage Instructions
### 1. Baseline Analysis
```sql
-- First, clear wait stats to establish a new baseline
DBCC SQLPERF('sys.dm_os_wait_stats', CLEAR);

-- Run workload, then analyze waits
-- Use the main query above
```

### 2. Regular Monitoring
```sql
-- Run during peak hours to identify bottlenecks
-- Focus on wait types with highest Percentage_WaitTime
```

### 3. Trending Analysis
```sql
-- Save results periodically to track changes over time
-- Look for increasing trends in specific wait types
```

## Interpretation Guidelines
### High Wait Time Indicators
- **> 30% total wait time**: Critical bottleneck requiring immediate attention
- **10-30% total wait time**: Significant issue needing investigation
- **< 10% total wait time**: Monitor for trends

### Actionable Thresholds
```sql
-- Common thresholds for investigation
WHERE Wait_Time_Seconds > 300  -- 5 minutes total wait time
   OR Percentage_WaitTime > 10  -- More than 10% of total waits
```

## Important Notes
1. **Cumulative Data**: Wait stats accumulate since last SQL Server restart or manual clear
2. **Context Matters**: Some waits are normal during specific operations
3. **Correlation**: Combine with other DMVs for complete picture
4. **Clearing Stats**: Use `DBCC SQLPERF('sys.dm_os_wait_stats', CLEAR)` cautiously in production

## Common Solutions by Wait Type
### For High CXPACKET Waits
- Update statistics regularly
- Consider adjusting MAXDOP settings
- Review and optimize expensive queries

### For High PAGEIOLATCH Waits
- Add more RAM
- Optimize disk subsystem
- Implement better indexing strategies
- Use SSDs for critical databases

### For High LCK_ Waits
- Optimize transaction design
- Use appropriate isolation levels
- Implement row versioning
- Review application locking patterns

This analysis helps identify the most significant performance bottlenecks in your SQL Server instance, guiding targeted optimization efforts.