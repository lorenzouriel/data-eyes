FROM python:3.11-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.11.24 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock /app/
COPY app /app/app
RUN uv sync --frozen --no-dev --no-editable

EXPOSE 8000

ENV PATH="/app/.venv/bin:$PATH"
RUN useradd --uid 10001 --create-home appuser
USER 10001:10001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
