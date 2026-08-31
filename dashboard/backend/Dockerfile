FROM python:3.11-slim

# pyodbc (app/mssql_client.py) needs an actual ODBC driver manager plus the
# Microsoft driver on the library path — python:3.11-slim ships neither.
# Without this, every connection to a monitored SQL Server fails at import
# time with "Can't open lib 'ODBC Driver 18 for SQL Server'".
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gnupg unixodbc-dev libgssapi-krb5-2 \
    && curl -sSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64,arm64,armhf signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && apt-get purge -y --auto-remove curl gnupg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml /app/
COPY app /app/app
COPY instances.yaml /app/instances.yaml

RUN pip install -e .

EXPOSE 8090

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
