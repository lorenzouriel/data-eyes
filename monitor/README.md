# Monitor

A comprehensive, production-ready monitoring solution for Microsoft SQL Server using Grafana and Prometheus. This solution provides real-time performance tracking, alerting, and historical analysis through pre-built dashboards and automated notifications.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Dashboards](#dashboards)
- [Monitoring Metrics](#monitoring-metrics)
- [Alerting](#alerting)
- [Documentation](#documentation)

## Overview

This monitoring stack provides enterprise-grade SQL Server observability with:
![dashboard](/monitor/docs/dashboard.png)

- **45+ pre-configured metrics** across 7 monitoring categories
- **2 Grafana dashboards** (comprehensive and simplified views)
- **Email alerting** via SMTP integration
- **Automated provisioning** with Docker Compose
- **Persistent storage** for historical data analysis

### Technologies Used

- **Grafana** (Latest) - Visualization and monitoring platform
- **Microsoft SQL Server** - Primary data source
- **Docker & Docker Compose** - Container orchestration

## Architecture

```bash
┌─────────────────────────────────────────────────────┐
│              Monitoring Solution                     │
└─────────────────────────────────────────────────────┘
                         │
              ┌──────────┴──────────┐
              │                     │
          ┌───▼────┐           ┌────▼─────┐
          │ Grafana│◄──────────┤  MSSQL   │
          │ :3000  │           │ Database │
          └────────┘           └──────────┘
              │
              ▼
          Email Alerts
          (SMTP/Gmail)
```

### Component Interaction

1. **Grafana** connects directly to SQL Server to execute monitoring queries
2. **Alert Manager** sends email notifications based on defined thresholds
3. **Docker Compose** orchestrates all services with persistent volumes

## Features

### Monitoring Coverage

- ✓ Server health and uptime tracking
- ✓ Query performance analysis
- ✓ Database space and growth monitoring
- ✓ SQL Agent job tracking
- ✓ Buffer pool and index management
- ✓ Lock and blocking detection
- ✓ Backup status verification
- ✓ Wait statistics analysis

### Operational Features

- ✓ Real-time dashboards with auto-refresh
- ✓ Email alerting on critical events
- ✓ Historical trend analysis
- ✓ Automated dashboard provisioning
- ✓ Secure credential management
- ✓ OAuth/Azure AD ready (optional)

## Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+
- SQL Server access credentials
- SMTP server access (Gmail configured by default)
- Network access to SQL Server instance

## Quick Start

### 1. Clone and Navigate
```bash
cd monitor/
```

### 2. Configure Environment
Create or edit the `.env` file with your credentials:
```bash
# Grafana Admin Credentials
GF_SECURITY_ADMIN_USER=admin
GF_SECURITY_ADMIN_PASSWORD=your_secure_password

# Email Configuration (SMTP)
GRAFANA_SMTP_HOST=smtp.gmail.com:587
GRAFANA_SMTP_USER=your_email@gmail.com
GRAFANA_SMTP_PASSWORD=your_app_password
GRAFANA_SMTP_FROM_ADDRESS=your_email@gmail.com
GRAFANA_SMTP_FROM_NAME=SQL Monitor
GRAFANA_NOTIFICATION_ADDRESSES=recipient@example.com

# SQL Server Connection
DB_HOST=your_server.com,port
DB_PORT=1433
DB_NAME=your_database
DB_USER=your_username
DB_PASSWORD=your_password

# Service URLs
PROMETHEUS_URL=http://prometheus:9090
DS_MSSQL=SQLServer
```

### 3. Launch Services
```bash
docker-compose up -d
```

### 4. Access Grafana
Open your browser to: `http://localhost:3000`

Login with credentials from `.env` file (default: admin/admin)

### 5. Verify Setup
1. Navigate to **Configuration → Data Sources**
2. Verify **SQLServer** shows green status
3. Go to **Dashboards** and select a pre-provisioned dashboard
4. Confirm metrics are displaying

## Configuration

### Directory Structure

```bash
monitor/
├── docker-compose.yml              # Service orchestration
├── .env                            # Environment variables (credentials)
├── .gitignore                      # Git exclusions
├── docs/                           # Monitoring documentation
│   ├── general.md                 # Server uptime, sessions
│   ├── server_performance.md      # Wait stats, locks, connections
│   ├── query_perfomance.md        # Query analytics, cache efficiency
│   ├── database_space_usage.md    # Storage, I/O, file management
│   ├── jobs_monitoring.md         # SQL Agent job tracking
│   ├── buffer_index_management.md # Memory, buffer pool, indexes
│   └── other_metrics.md           # Backups, availability, alerts
└── grafana/
    ├── grafana.ini                # Grafana configuration
    ├── datasources.yml            # Data source definitions
    ├── alerts-and-notifiers.yml   # Alert routing
    ├── dashboard-provider.yml     # Dashboard provisioning
    └── dashboards/
        ├── sqlserver.json         # Comprehensive dashboard
        └── sql_server_simplified.json # Simplified dashboard
```

### Key Configuration Files

#### `grafana.ini`
Main Grafana configuration including:
- SMTP settings for email alerts
- Server configuration (port, root URL)
- Authentication options (Azure AD, OAuth templates)

#### `datasources.yml`
Defines connections to:
- **Prometheus** - Time-series backend
- **Microsoft SQL Server** - Primary monitoring target

#### `alerts-and-notifiers.yml`
Email notification routing:
- Contact points configuration
- Alert routing rules
- Email recipient management

## Dashboards

### 1. Microsoft SQL Server Dashboard (Comprehensive)

**File:** [grafana/dashboards/sqlserver.json](grafana/dashboards/sqlserver.json)

**Sections:**
- General (Active Sessions, Uptime)
- Query Performance (Top 10 Queries, Cache Hit Rate, Latency)
- Server Performance (Threads, Locks, Connections, Wait Times)
- Buffer & Index Management (Hit Rate, Usage Stats, PLE)
- Database Space Usage (Size, Files, Transaction Logs)
- Backup Status (History, Types)
- Jobs Monitoring (Execution, Failures, History)

**Panels:** 45+ visualizations

### 2. Microsoft SQL Server Dashboard Simplified

**File:** [grafana/dashboards/sql_server_simplified.json](grafana/dashboards/sql_server_simplified.json)

Streamlined view with essential metrics:
- Collapsed general section
- Focused query performance
- Core server health indicators
- Critical space and job metrics

**Panels:** 30+ visualizations

### Dashboard Features

- Auto-refresh intervals (configurable)
- Color-coded thresholds (green/yellow/red)
- Time range selection
- Variable filtering
- Export to PDF/PNG
- Panel zoom and inspect

## Monitoring Metrics

### Server Health
- SQL Server uptime
- Active user sessions
- Current connections (idle vs. active)
- Database availability percentage

### Query Performance
- Top 10 longest-running queries
- Queries per second
- Query cache hit rate
- Query latency and execution time
- Execution plan performance
- CPU-intensive queries
- High logical read queries

### Resource Utilization
- Buffer pool hit rate and usage
- Page Life Expectancy (PLE)
- Memory grants pending
- Memory usage by session
- System memory status
- Temp tables created on disk

### Storage Management
- Database size (total, used, unused)
- Transaction log space usage
- Database file information
- Row counts per table
- Disk I/O statistics

### SQL Agent Jobs
- Job execution frequency
- Currently running jobs
- Job run history and duration
- Failed jobs with error messages
- Scheduled vs. running jobs overview

### Performance Analysis
- Wait statistics by type
- Lock monitoring (blocking, deadlocks)
- Active transactions
- Index usage statistics
- Cache efficiency metrics

### Backup & Recovery
- Backup status and history
- Last successful backup timestamp
- Backup types (FULL, DIFFERENTIAL, LOG)

## Alerting

### Email Notifications

Configured via `.env` file:

```bash
GRAFANA_SMTP_HOST=smtp.gmail.com:587
GRAFANA_SMTP_USER=your_email@gmail.com
GRAFANA_SMTP_PASSWORD=your_app_password
GRAFANA_NOTIFICATION_ADDRESSES=recipient@example.com
```

### Setting Up Gmail SMTP

1. Enable 2-factor authentication on your Google account
2. Generate an App Password: [Google App Passwords](https://myaccount.google.com/apppasswords)
3. Use the app password in `GRAFANA_SMTP_PASSWORD`

### Alert Configuration

Alerts can be configured in Grafana UI:
1. Open a dashboard panel
2. Click **Edit** → **Alert** tab
3. Define alert conditions (thresholds, evaluation intervals)
4. Select notification channel (email configured by default)
5. Save dashboard

### Pre-configured Alert Examples

See [docs/other_metrics.md](docs/other_metrics.md) for alert queries:
- Long-running queries (>30 seconds)
- Failed backups
- Low buffer pool hit rate
- High memory pressure
- Job failures

## Documentation

Detailed SQL queries and metric explanations are available in the `docs/` directory:

| Document | Description |
|----------|-------------|
| [general.md](docs/general.md) | Database context, uptime, active sessions |
| [server_performance.md](docs/server_performance.md) | Wait stats, locks, connections, transactions |
| [query_perfomance.md](docs/query_perfomance.md) | Query analytics, execution plans, cache |
| [database_space_usage.md](docs/database_space_usage.md) | Storage, files, I/O statistics |
| [jobs_monitoring.md](docs/jobs_monitoring.md) | SQL Agent job tracking and history |
| [buffer_index_management.md](docs/buffer_index_management.md) | Memory, buffer pool, index usage |
| [other_metrics.md](docs/other_metrics.md) | Backups, availability, alerts |

Each document includes:
- Metric description and purpose
- SQL query source code
- Use cases and interpretation
- Threshold recommendations

## Maintenance

### Backup Dashboard Configuration

```bash
# Export dashboards
docker exec grafana grafana-cli admin export-dashboard > backup.json

# Backup volumes
docker run --rm -v monitor_grafana_data:/data -v $(pwd):/backup ubuntu tar czf /backup/grafana-backup.tar.gz /data
```

### Update Services

```bash
# Pull latest images
docker-compose pull

# Recreate containers
docker-compose up -d --force-recreate
```

### Clean Up Old Data

```bash
# Prometheus data retention (edit prometheus.yml)
# Default: 15 days

# Grafana cleanup
docker exec grafana grafana-cli admin cleanup-dashboard
```