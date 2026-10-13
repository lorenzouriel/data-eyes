"""
Data Eyes agent API (internal only; it has no sign-in of its own).

GET  /api/agent/status  provider, model, and whether the agent can answer
POST /api/agent/ask     Server-Sent Events: `status` (progress), `text`
                        (answer), `error`, then `done`
"""
import asyncio
import json
import logging
from typing import List, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.agent import answer
from app.config import settings, status

LOG = logging.getLogger("data_eyes_agent")
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
slots = asyncio.Semaphore(settings.AI_MAX_CONCURRENT_ASKS)


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class AskRequest(BaseModel):
    messages: List[Message] = Field(min_length=1, max_length=40)

    @field_validator("messages")
    @classmethod
    def last_is_question(cls, messages):
        if messages[-1].role != "user" or not messages[-1].content.strip():
            raise ValueError("the last message must be the user's question")
        return messages


def frame(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


@app.get("/health")
async def health():
    return Response(status_code=200)


@app.get("/api/agent/status")
async def agent_status():
    return status()


@app.post("/api/agent/ask")
async def ask(request: AskRequest):
    current = status()
    if not current["configured"]:
        raise HTTPException(status_code=503, detail=current["reason"])
    if slots.locked():
        raise HTTPException(status_code=429, detail="The assistant is busy; try again in a moment.")
    # Empty assistant turns (a failed earlier answer) carry nothing for the model.
    history = [m.model_dump() for m in request.messages if m.content.strip()]

    async def events():
        queue: asyncio.Queue = asyncio.Queue()
        separator = {"needed": False}

        async def emit(kind: str, text: str):
            if kind == "text":
                # Separate the text of successive model turns.
                text = ("\n\n" if separator["needed"] else "") + text.strip()
                separator["needed"] = True
            await queue.put(frame(kind, {"text": text}))

        async def run():
            async with slots:
                try:
                    await answer(history, emit)
                except Exception as exc:
                    # Never log or return keys, prompts or provider response bodies.
                    LOG.warning("Ask failed provider=%s error=%s", settings.AI_PROVIDER, type(exc).__name__)
                    await queue.put(frame("error", {"error": f"The AI provider request failed ({type(exc).__name__})."}))
                finally:
                    await queue.put(None)

        task = asyncio.create_task(run())
        try:
            while (item := await queue.get()) is not None:
                yield item
            yield frame("done", {})
        finally:
            task.cancel()

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
