# How to Use Data Eyes MCP Server
Complete guide for installing, configuring, and using the Data Eyes MCP Server to give Claude (or other MCP clients) secure access to your SQL Server databases.

## Table of Contents
1. [What is This?](#what-is-this)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Running the Server](#running-the-server)
6. [Integration with Claude Desktop](#integration-with-claude-desktop)
7. [Integration with CrewAI](#integration-with-crewai)
8. [Usage Examples](#usage-examples)
9. [Troubleshooting](#troubleshooting)
11. [Advanced Configuration](#advanced-configuration)
12. [Additional Resources](#additional-resources)

## What is This?
The Data Eyes MCP Server is a **Model Context Protocol (MCP)** server that enables Large Language Models like Claude to interact safely with Microsoft SQL Server databases. It provides:
- **7 MCP tools** for database querying and exploration
- **Read-only mode by default** for maximum safety
- **SQL injection prevention** through policy validation
- **Query timeouts and row limits** to prevent resource exhaustion
- **Structured logging and metrics** for observability
- **Health check endpoints** for monitoring

### Use Cases
- **Data Analysis**: Ask Claude to analyze your database tables
- **Report Generation**: Generate reports from database queries
- **Schema Exploration**: Discover and understand database structure
- **Query Assistance**: Get help writing complex SQL queries
- **Data Validation**: Check data integrity across tables

## Prerequisites
### System Requirements
- **Python**: 3.8 or higher
- **SQL Server**: 2012 or higher (or Azure SQL)
- **ODBC Driver**: Microsoft ODBC Driver 17 or 18 for SQL Server
- **Operating System**: Windows, Linux, or macOS

### For Windows
1. Install Python 3.8+: https://www.python.org/downloads/
2. Install ODBC Driver 17: https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server

### For Linux (Ubuntu/Debian)
```bash
# Install Python
sudo apt-get update
sudo apt-get install python3 python3-pip

# Install ODBC Driver 17
curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -
curl https://packages.microsoft.com/config/ubuntu/20.04/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
sudo apt-get update
sudo ACCEPT_EULA=Y apt-get install msodbcsql17 unixodbc-dev
```

### For macOS
```bash
# Install Python (via Homebrew)
brew install python3

# Install ODBC Driver
brew tap microsoft/mssql-release https://github.com/Microsoft/homebrew-mssql-release
brew update
brew install msodbcsql17
```

## Installation
### Method 1: From Source (Recommended for Development)
```bash
# Clone or download the repository
cd /path/to/data-eyes/mcp

# Install dependencies
pip install -r requirements.txt

# Or install in development mode
pip install -e .
```

### Method 2: Using Docker (Recommended for Production)
```bash
# Build the Docker image
docker build -t data-eyes-mcp:latest .

# Run the container
docker run -i --rm \
  -e MSSQL_CONNECTION_STRING="Driver={ODBC Driver 17 for SQL Server};Server=..." \
  data-eyes-mcp:latest
```

### Verify Installation
```bash
# Check if installation was successful
python -m data_eyes_mcp.cli --version

# Output: data_eyes_mcp.cli 0.1.0
```

## Configuration
### Connection String
The most important configuration is your database connection string. You have several options:

#### Option 1: Environment Variable
```bash
export MSSQL_CONNECTION_STRING="Driver={ODBC Driver 17 for SQL Server};Server=localhost,1433;Database=mydb;UID=username;PWD=password"
```

#### Option 2: .env File
Create a `.env` file in the project root:
```env
# Database Connection
MSSQL_CONNECTION_STRING=Driver={ODBC Driver 17 for SQL Server};Server=localhost,1433;Database=mydb;UID=username;PWD=password

# Timeouts
MSSQL_CONNECTION_TIMEOUT=5
MSSQL_QUERY_TIMEOUT=30

# Security
READ_ONLY=true
ENABLE_WRITES=false

# Limits
MAX_ROWS_PER_QUERY=50000
MAX_QUERY_LENGTH=50000

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

### Connection String Examples
#### Windows Authentication
```
Driver={ODBC Driver 17 for SQL Server};Server=localhost;Database=mydb;Trusted_Connection=yes
```

#### SQL Server Authentication
```
Driver={ODBC Driver 17 for SQL Server};Server=localhost,1433;Database=mydb;UID=sa;PWD=YourPassword
```

#### Azure SQL Database
```
Driver={ODBC Driver 17 for SQL Server};Server=myserver.database.windows.net;Database=mydb;UID=admin@myserver;PWD=password;Encrypt=yes;TrustServerCertificate=no
```

#### Named Instance
```
Driver={ODBC Driver 17 for SQL Server};Server=localhost\SQLEXPRESS;Database=mydb;Trusted_Connection=yes
```

### Configuration Options
| Setting | Default | Description |
|---------|---------|-------------|
| `MSSQL_CONNECTION_STRING` | **Required** | Database connection string |
| `MSSQL_CONNECTION_TIMEOUT` | `30` | Connection timeout in seconds |
| `MSSQL_QUERY_TIMEOUT` | `30` | Query execution timeout in seconds |
| `MSSQL_MAX_POOL_SIZE` | `10` | Maximum connection pool size |
| `READ_ONLY` | `true` | Enforce read-only mode |
| `ENABLE_WRITES` | `false` | Allow INSERT/UPDATE/DELETE |
| `ADMIN_CONFIRM` | `""` | Token required to enable writes |
| `MAX_ROWS_PER_QUERY` | `50000` | Maximum rows returned per query |
| `MAX_QUERY_LENGTH` | `50000` | Maximum query length in characters |
| `MCP_TRANSPORT` | `stdio` | Transport: `stdio` or `http` |
| `HTTP_BIND_HOST` | `127.0.0.1` | HTTP server bind address |
| `HTTP_BIND_PORT` | `8080` | HTTP server port |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG/INFO/WARNING/ERROR) |
| `LOG_FORMAT` | `json` | Log format: `json` or `text` |
| `ENABLE_METRICS` | `true` | Enable Prometheus metrics |
| `RATE_LIMIT_ENABLED` | `false` | Enable rate limiting |

## Running the Server
### Method 1: Stdio Transport (For MCP Clients like Claude)
This is the default mode for integration with Claude Desktop:
```bash
python -m data_eyes_mcp.cli
```

The server will wait for JSON-RPC messages on stdin and respond on stdout.

### Method 2: HTTP Transport (For Testing/Development)
Run the server as an HTTP API:
```bash
python -m data_eyes_mcp.cli --transport http --bind 0.0.0.0:8080
```

Then access the endpoints:
```bash
# Health check
curl http://localhost:8080/health

# Readiness check
curl http://localhost:8080/ready

# Server info
curl http://localhost:8080/info

# Prometheus metrics
curl http://localhost:8080/metrics
```

### Method 3: Docker
```bash
# Using environment variables
docker run -i --rm \
  -e MSSQL_CONNECTION_STRING="Driver={ODBC Driver 17 for SQL Server};Server=host.docker.internal,1433;Database=mydb;UID=user;PWD=pass" \
  data-eyes-mcp:latest

# Using env file
docker run -i --rm --env-file .env data-eyes-mcp:latest

# HTTP mode with port mapping
docker run --rm -p 8080:8080 \
  -e MSSQL_CONNECTION_STRING="..." \
  data-eyes-mcp:latest \
  --transport http --bind 0.0.0.0:8080
```

### Command-Line Options
```bash
python -m data_eyes_mcp.cli --help
```

Options:
- `--transport {stdio,http}` - Transport mechanism (default: stdio)
- `--bind HOST:PORT` - Bind address for HTTP (default: 127.0.0.1:8080)
- `--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}` - Logging level
- `--log-format {json,text}` - Log output format
- `--version` - Show version and exit

## Integration with Claude Desktop
### Step 1: Build the Docker Image
```bash
cd /path/to/data-eyes/mcp
docker build -t data-eyes-mcp:latest .
```

### Step 2: Configure Claude Desktop
Edit the Claude Desktop configuration file:
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Linux**: `~/.config/Claude/claude_desktop_config.json`

Add the MCP server configuration:
```json
{
  "mcpServers": {
    "mssql": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e",
        "MSSQL_CONNECTION_STRING=Driver={ODBC Driver 17 for SQL Server};Server=YOUR_SERVER;Database=YOUR_DB;UID=YOUR_USER;PWD=YOUR_PASSWORD;TrustServerCertificate=yes;",
        "data-eyes-mcp:latest"
      ]
    }
  }
}
```

### Step 3: Restart Claude Desktop
Close and reopen Claude Desktop. The MCP server will be available.

### Step 4: Test the Integration
In Claude Desktop, try asking:
```
Can you list all the schemas in my database?
```

or

```
Show me the tables in the dbo schema.
```

Claude will now have access to the 7 MCP tools provided by the server!

## Integration with CrewAI

CrewAI is an AI agent framework that allows you to create collaborative AI agents. You can connect CrewAI agents to your Data Eyes MCP Server to give them database access capabilities.

### Prerequisites for CrewAI Integration

```bash
# Install CrewAI and tools
pip install crewai crewai-tools
```

### Step 1: Start the MCP Server with HTTP Transport

```bash
python -m data_eyes_mcp.cli --transport http --bind 127.0.0.1:8080
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8080 (Press CTRL+C to quit)
```

### Step 2: Create a CrewAI Script

Create a file `analyze_database.py`:

```python
from crewai import Agent, Task, Crew
from crewai_tools import MCPServerAdapter

# Configure MCP server connection
server_params = {
    "url": "http://localhost:8080/mcp",
    "transport": "streamable-http"
}

# Connect to MCP server and get tools
with MCPServerAdapter(server_params, connect_timeout=60) as mcp_tools:
    # Create a database analyst agent
    db_analyst = Agent(
        role="Database Analyst",
        goal="Analyze SQL Server database and provide insights",
        backstory="You are an expert database analyst who can query databases, "
                 "explore schemas, and extract meaningful insights from data.",
        tools=mcp_tools,  # All MCP tools are automatically available
        verbose=True
    )

    # Create an analysis task
    analysis_task = Task(
        description="""
        Perform a comprehensive database analysis:
        1. Check if the database connection is healthy
        2. List all available schemas
        3. For the 'dbo' schema, list all tables
        4. Get information about the database server
        5. Provide a summary of your findings
        """,
        expected_output="A detailed report of the database structure",
        agent=db_analyst
    )

    # Create and run the crew
    crew = Crew(
        agents=[db_analyst],
        tasks=[analysis_task],
        verbose=True
    )

    # Execute the analysis
    result = crew.kickoff()
    print(result)
```

### Step 3: Run the CrewAI Script

```bash
python analyze_database.py
```

## Usage Examples
### Example 1: Basic Data Query
**User prompt to Claude:**
```
Show me the top 10 customers by total order value from the database.
```

**Claude will:**
1. Call `list_tables()` to find customer and order tables
2. Call `schema_discovery()` to understand table structure
3. Call `execute_sql()` with appropriate JOIN query
4. Format and present the results

### Example 2: Schema Exploration
**User prompt:**
```
What tables are in the sales schema and what columns do they have?
```

**Claude will:**
1. Call `list_tables(schema="sales")`
2. Call `schema_discovery(schema="sales")`
3. Present a formatted summary of tables and columns

### Example 3: Data Analysis
**User prompt:**
```
Analyze the distribution of orders by month for the last year.
```

**Claude will:**
1. Discover relevant tables
2. Execute SQL with GROUP BY and date functions
3. Present results and create visualizations (if supported)

### Example 4: Direct SQL Execution
**User prompt:**
```
Execute this query: SELECT COUNT(*) as total_users FROM users WHERE created_date >= '2024-01-01'
```

**Claude will:**
1. Call `execute_sql(sql="SELECT COUNT(*) as total_users FROM users WHERE created_date >= '2024-01-01'")`
2. Return the count

### Example 5: Export to CSV
**User prompt:**
```
Export the product list to CSV format.
```

**Claude will:**
1. Call `execute_sql(sql="SELECT * FROM products", format="csv")`
2. Return CSV-formatted data

### Example 6: Check Connection
**User prompt:**
```
Is the database connection working?
```

**Claude will:**
1. Call `check_db_connection()`
2. Report the status

### Recommended Practices
#### 1. Use Read-Only Database User
Create a dedicated read-only user for the MCP server:
```sql
-- Create login
CREATE LOGIN mcp_readonly WITH PASSWORD = 'mcp_readonly';

-- Create user in database
USE YourDatabase;
CREATE USER mcp_readonly FOR LOGIN mcp_readonly;

-- Grant read-only access
ALTER ROLE db_datareader ADD MEMBER mcp_readonly;

-- Deny write permissions
DENY INSERT, UPDATE, DELETE, ALTER, CREATE, DROP TO mcp_readonly;
```

#### 2. Network Security
- **Firewall**: Only allow connections from trusted IPs
- **SSL/TLS**: Use encrypted connections (`Encrypt=yes` in connection string)
- **VPN**: Run server on internal network or VPN

#### 3. Resource Limits
Set conservative limits:
```env
MSSQL_QUERY_TIMEOUT=30      # Prevent runaway queries
MAX_ROWS_PER_QUERY=10000    # Limit result set size
MSSQL_CONNECTION_TIMEOUT=5  # Fast connection failure
```

#### 4. Monitoring
Enable metrics and monitor for:
- Unusual query patterns
- Failed authentication attempts
- Blocked queries
- Query performance issues

#### 5. Log Management
```env
LOG_LEVEL=INFO
LOG_FORMAT=json
```

Send logs to centralized logging (Splunk, ELK, CloudWatch)

### Enabling Write Operations (Advanced)
⚠️ **DANGER**: Only enable if absolutely necessary

```env
READ_ONLY=false
ENABLE_WRITES=true
ADMIN_CONFIRM=your_secret_token_here
```

With writes enabled:
- Use a database user with minimal write permissions
- Test thoroughly in non-production environment first
- Monitor all write operations closely
- Consider separate MCP server instance for writes

## Troubleshooting

### Connection Issues

#### Problem: "Failed to connect to database"

**Solutions:**
1. Verify connection string is correct
2. Check SQL Server is running and accessible
3. Verify firewall allows connections on SQL port (1433)
4. Test connection with `sqlcmd` or SQL Server Management Studio
5. Check ODBC driver is installed: `odbcinst -q -d`

#### Problem: "ODBC Driver not found"

**Solutions:**
```bash
# Linux
sudo ACCEPT_EULA=Y apt-get install msodbcsql17

# macOS
brew install msodbcsql17

# Windows
# Download from: https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server
```

### Query Issues

#### Problem: "Query not allowed - contains write operation"

**Cause:** Server is in read-only mode (default)

**Solution:** This is by design. To enable writes, see [Enabling Write Operations](#enabling-write-operations-advanced)

#### Problem: "Query timeout"

**Solutions:**
1. Optimize the query (add indexes, reduce joins)
2. Increase timeout: `MSSQL_QUERY_TIMEOUT=60`
3. Use TOP or WHERE clause to limit rows

#### Problem: "Query exceeds maximum length"

**Solution:** Increase limit:
```env
MAX_QUERY_LENGTH=100000
```

### Integration Issues

#### Problem: Claude doesn't see the MCP server

**Solutions:**
1. Check `claude_desktop_config.json` syntax is valid JSON
2. Verify Docker image is built: `docker images | grep data-eyes-mcp`
3. Restart Claude Desktop completely
4. Check Claude Desktop logs: `%APPDATA%\Claude\logs\` (Windows)

#### Problem: "Docker: command not found"
**Solution:** Install Docker Desktop or use Python directly:
```json
{
  "mcpServers": {
    "data-eyes-mcp": {
      "command": "python",
      "args": [
        "-m",
        "data_eyes_mcp.cli"
      ],
      "env": {
        "MSSQL_CONNECTION_STRING": "Driver={ODBC Driver 17 for SQL Server};..."
      }
    }
  }
}
```

### Performance Issues
#### Problem: Slow query execution
**Solutions:**
1. Add database indexes on frequently queried columns
2. Use query hints (WITH (NOLOCK) for read-only)
3. Increase connection pool size: `MSSQL_MAX_POOL_SIZE=20`
4. Check SQL Server performance metrics

#### Problem: High memory usage
**Solutions:**
1. Reduce `MAX_ROWS_PER_QUERY`
2. Use pagination with TOP and OFFSET
3. Request CSV format instead of JSON (more compact)

## Advanced Configuration
### Custom Policy Rules
Edit [src/data_eyes_mcp/policy.py](src/data_eyes_mcp/policy.py:27) to customize banned patterns:

```python
READ_ONLY_BANNED_PATTERNS = [
    r"\bDROP\b",
    r"\bALTER\b",
    # Add your custom patterns
]
```

### Rate Limiting
Enable rate limiting to prevent abuse:

```env
RATE_LIMIT_ENABLED=true
RATE_LIMIT_QUERIES_PER_MINUTE=100
```

### Prometheus Metrics
Access metrics at `/metrics` endpoint (HTTP mode):

```bash
curl http://localhost:8080/metrics
```

Metrics include:
- `mssql_queries_executed_total` - Total queries by tool and status
- `mssql_query_duration_seconds` - Query latency histogram
- `mssql_query_rows_returned` - Result set size histogram
- `mssql_active_queries` - Currently executing queries
- `mssql_server_ready` - Server readiness status

### Multiple Database Support
Run multiple MCP server instances for different databases:

```json
{
  "mcpServers": {
    "mssql-prod": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-e", "MSSQL_CONNECTION_STRING=...", "data-eyes-mcp:latest"]
    },
    "mssql-staging": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-e", "MSSQL_CONNECTION_STRING=...", "data-eyes-mcp:latest"]
    }
  }
}
```

### Custom Tool Development
Add new tools by editing [src/data_eyes_mcp/tools.py](src/data_eyes_mcp/tools.py):
```python
@mcp.tool()
async def my_custom_tool(param: str) -> str:
    """My custom tool description."""
    # Implementation
    return "result"
```

## Additional Resources
- **Main README**: See [README.md](README.md)
- **MCP Specification**: https://modelcontextprotocol.io/
- **SQL Server Documentation**: https://learn.microsoft.com/en-us/sql/