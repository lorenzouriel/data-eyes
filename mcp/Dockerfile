FROM python:3.11-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.11.24 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md /app/
COPY src /app/src
RUN uv sync --frozen --no-dev --no-editable

ENV PATH="/app/.venv/bin:$PATH"
RUN useradd --uid 10001 --create-home appuser
USER 10001:10001

CMD ["python", "-m", "data_eyes_mcp.main"]
