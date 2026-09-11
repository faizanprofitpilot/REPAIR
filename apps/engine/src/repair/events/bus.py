"""Typed event bus with JSONL sink and SSE fan-out."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Callable


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Event:
    type: str
    payload: dict[str, Any]
    run_id: str
    seq: int
    ts: str = field(default_factory=utcnow_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "run_id": self.run_id,
            "seq": self.seq,
            "type": self.type,
            "payload": self.payload,
        }


class EventBus:
    def __init__(self, runs_dir: Path | None = None) -> None:
        self._seq: dict[str, int] = defaultdict(int)
        self._buffers: dict[str, list[Event]] = defaultdict(list)
        self._queues: dict[str, list[asyncio.Queue[Event | None]]] = defaultdict(list)
        self._runs_dir = runs_dir
        self._listeners: list[Callable[[Event], None]] = []
        self._fault_active = False
        self._fault_detail: dict[str, Any] = {}
        self._registry_version: str = "V1"
        self._state: dict[str, Any] = {}

    def set_runs_dir(self, path: Path) -> None:
        self._runs_dir = path
        path.mkdir(parents=True, exist_ok=True)

    def set_fault_active(self, active: bool, detail: dict[str, Any] | None = None) -> None:
        self._fault_active = active
        self._fault_detail = detail or {}

    def set_registry_version(self, version: str) -> None:
        self._registry_version = version

    def update_state(self, **kwargs: Any) -> None:
        self._state.update(kwargs)

    def get_public_state(self) -> dict[str, Any]:
        return {
            "fault_active": self._fault_active,
            "fault_detail": self._fault_detail,
            "registry_version": self._registry_version,
            **self._state,
        }

    def emit(self, run_id: str, event_type: str, payload: dict[str, Any] | None = None) -> Event:
        self._seq[run_id] += 1
        event = Event(
            type=event_type,
            payload=payload or {},
            run_id=run_id,
            seq=self._seq[run_id],
        )
        self._buffers[run_id].append(event)
        if self._runs_dir:
            path = self._runs_dir / run_id / "events.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict()) + "\n")
        for q in list(self._queues[run_id]):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass
        for listener in self._listeners:
            try:
                listener(event)
            except Exception:
                pass
        return event

    def history(self, run_id: str) -> list[Event]:
        return list(self._buffers.get(run_id, []))

    def subscribe(self, run_id: str) -> asyncio.Queue[Event | None]:
        q: asyncio.Queue[Event | None] = asyncio.Queue()
        self._queues[run_id].append(q)
        return q

    def unsubscribe(self, run_id: str, q: asyncio.Queue[Event | None]) -> None:
        if q in self._queues[run_id]:
            self._queues[run_id].remove(q)

    async def stream(self, run_id: str) -> AsyncIterator[Event]:
        for event in self.history(run_id):
            yield event
        q = self.subscribe(run_id)
        try:
            while True:
                item = await q.get()
                if item is None:
                    break
                yield item
        finally:
            self.unsubscribe(run_id, q)

    def close_run(self, run_id: str) -> None:
        for q in list(self._queues[run_id]):
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass


# Process-wide bus used by API and scenarios
bus = EventBus()
