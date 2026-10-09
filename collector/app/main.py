"""Cached Prometheus exporter. HTTP requests never execute SQL."""
import asyncio
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST
from app.scheduler import Exporter
from app.config import load_instances, load_check_settings

registry = CollectorRegistry()


@asynccontextmanager
async def lifespan(app):
    exporter = Exporter(load_instances(), load_check_settings())
    registry.register(exporter)
    task = asyncio.create_task(exporter.run())
    app.state.task = task
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        registry.unregister(exporter)


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)


@app.get("/health")
async def health():
    return Response(status_code=503 if app.state.task.done() else 200)


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(registry), headers={"Content-Type": CONTENT_TYPE_LATEST})
