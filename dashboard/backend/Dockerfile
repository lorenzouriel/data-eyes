FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml /app/
COPY app /app/app
COPY instances.yaml /app/instances.yaml

RUN pip install -e .

EXPOSE 8090

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
