"""SSE stream: broadcast appended events to the WebUI (single global channel)."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from apm.core import events, projections
from apm.core.bus import event_bus

router = APIRouter(tags=["stream"])


@router.get("/stream")
async def stream(request: Request, since_id: int = 0, project_id: str | None = None) -> EventSourceResponse:
    projections.ensure_handlers_registered()

    async def gen():
        queue = event_bus.subscribe()
        try:
            # Catch-up: replay anything already logged after since_id.
            if since_id > 0:
                evts, _ = events.query_events(since_id=since_id, limit=1000)
                for e in reversed(evts):
                    if project_id and e.project_id != project_id:
                        continue
                    yield {"event": "apm", "data": json.dumps(e.as_dict(), ensure_ascii=False)}
            elif project_id is None:
                yield {"event": "ready", "data": "{}"}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue
                if project_id and event.get("project_id") != project_id:
                    continue
                yield {"event": "apm", "data": json.dumps(event, ensure_ascii=False)}
        finally:
            event_bus.unsubscribe(queue)

    return EventSourceResponse(gen())
