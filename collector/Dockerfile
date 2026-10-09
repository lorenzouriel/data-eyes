FROM python:3.11-slim-bookworm

# pyodbc (app/sql.py) needs an actual ODBC driver manager plus the
# Microsoft driver on the library path — python:3.11-slim ships neither.
# Without this, every connection to a monitored SQL Server fails at import
# time with "Can't open lib 'ODBC Driver 18 for SQL Server'".
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gnupg unixodbc libgssapi-krb5-2 \
    && curl -sSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64,arm64,armhf signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql17 msodbcsql18 \
    && apt-get purge -y --auto-remove curl gnupg \
    && rm -rf /var/lib/apt/lists/*

# Reuse connections instead of a new TCP + TLS login per query. unixODBC
# pools only with Pooling=Yes and a positive CPTimeout (seconds an idle
# connection is kept; longer than the 30-second collection interval). Both
# drivers reset a reused session, so temp tables do not leak between queries.
RUN sed -i '1i [ODBC]\nPooling=Yes\n' /etc/odbcinst.ini \
    && sed -i '/^\[ODBC Driver 1[78] for SQL Server\]/a CPTimeout=120' /etc/odbcinst.ini

COPY --from=ghcr.io/astral-sh/uv:0.11.24 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock /app/
COPY app /app/app
COPY checks.yaml /app/checks.yaml
RUN uv sync --frozen --no-dev --no-editable

EXPOSE 8090

ENV PATH="/app/.venv/bin:$PATH"
RUN useradd --uid 10001 --create-home appuser && mkdir /state && chown 10001:10001 /state
USER 10001:10001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
