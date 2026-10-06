# Dockerfile
FROM python:3.11-slim-bookworm

# Install both supported SQL Server ODBC driver versions so every service can
# consume the same instances.yaml without image-specific driver overrides.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg unixodbc unixodbc-dev libgssapi-krb5-2 \
    && curl -sSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64,arm64,armhf signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/data-eyes-mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql17 msodbcsql18 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.24 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock /app/
COPY src /app/src

COPY README.md /app/
RUN uv sync --frozen --no-dev --no-editable

ENV PATH="/app/.venv/bin:$PATH"
RUN useradd --uid 10001 --create-home appuser
USER 10001:10001

CMD ["python", "-m", "data_eyes_mcp.cli"]
