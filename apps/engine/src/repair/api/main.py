"""FastAPI: POST /demo/run, GET /events (SSE), GET /state."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from repair.agent.support_agent import prompt_hash
from repair.config import get_settings
from repair.events.bus import bus
from repair.scenarios.demo import run_demo

app = FastAPI(title="REPAIR", version="0.1.0")

settings = get_settings()
bus.set_runs_dir(settings.runs_dir)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.repair_web_origin,
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_demo_lock = asyncio.Lock()
_last_run_id: str | None = None


def _run_demo_sync(run_id: str, phases: list[str] | None, skip_learn: bool) -> dict[str, Any]:
    return run_demo(run_id=run_id, phases=phases, skip_learning_if_promoted=skip_learn)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "prompt_hash": prompt_hash(),
        "credentials": settings.missing_credentials(),
        "registry_version": bus.get_public_state().get("registry_version", "unknown"),
    }


@app.get("/state")
def state() -> dict[str, Any]:
    public = bus.get_public_state()
    return {
        **public,
        "last_run_id": _last_run_id,
        "prompt_hash": prompt_hash(),
        "credentials": settings.missing_credentials(),
    }


@app.post("/demo/run")
async def demo_run(
    background_tasks: BackgroundTasks,
    phases: str | None = Query(default=None, description="comma-separated phases"),
    force_learn: bool = Query(default=False),
    wait: bool = Query(default=False, description="block until demo finishes"),
) -> JSONResponse:
    global _last_run_id
    if _demo_lock.locked():
        return JSONResponse({"ok": False, "error": "demo_already_running", "run_id": _last_run_id}, status_code=409)

    run_id = f"demo-{uuid.uuid4().hex[:10]}"
    _last_run_id = run_id
    phase_list = [p.strip() for p in (phases or "").split(",") if p.strip()] or None
    skip_learn = not force_learn

    async def _guarded() -> None:
        async with _demo_lock:
            await asyncio.to_thread(_run_demo_sync, run_id, phase_list, skip_learn)

    if wait:
        async with _demo_lock:
            result = await asyncio.to_thread(_run_demo_sync, run_id, phase_list, skip_learn)
        return JSONResponse({"ok": True, "run_id": run_id, "result": result})

    background_tasks.add_task(_guarded)
    return JSONResponse({"ok": True, "run_id": run_id, "status": "started", "phases": phase_list})


@app.get("/events")
async def events(run_id: str = Query(...)) -> EventSourceResponse:
    async def gen():
        async for event in bus.stream(run_id):
            yield {
                "event": event.type,
                "id": str(event.seq),
                "data": json.dumps(event.to_dict()),
            }

    return EventSourceResponse(gen())


def main() -> None:
    import uvicorn

    uvicorn.run(
        "repair.api.main:app",
        host="0.0.0.0",
        port=settings.repair_engine_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
