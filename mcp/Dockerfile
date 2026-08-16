# Dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y unixodbc && rm -rf /var/lib/apt/lists/*

# Install ODBC driver 17 for SQL Server
RUN apt-get update && apt-get install -y curl gnupg && \
    curl -sSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/11/prod bullseye main" > /etc/apt/sources.list.d/data-eyes-mssql-release.list && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y msodbcsql17 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/
COPY src /app/src

RUN pip install -e /app

CMD ["python", "-m", "data_eyes_mcp.cli"]