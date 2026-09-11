"""Controlled CommitThenDisconnect fault injector."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FaultInjector:
    mode: str = "CommitThenDisconnect"
    armed_tools: set[str] = field(default_factory=set)
    once: bool = True
    _fired: set[str] = field(default_factory=set)
    last_injection: dict[str, Any] | None = None

    def arm(self, tool_id: str, *, once: bool = True) -> None:
        self.armed_tools.add(tool_id)
        self.once = once
        self._fired.discard(tool_id)
        self.last_injection = None

    def disarm(self, tool_id: str | None = None) -> None:
        if tool_id is None:
            self.armed_tools.clear()
            self._fired.clear()
        else:
            self.armed_tools.discard(tool_id)
            self._fired.discard(tool_id)

    def is_active(self) -> bool:
        return bool(self.armed_tools)

    def should_inject(self, tool_id: str, upstream_ok: bool) -> bool:
        if not upstream_ok:
            return False
        if tool_id not in self.armed_tools:
            return False
        if self.once and tool_id in self._fired:
            return False
        return True

    def inject(self, tool_id: str) -> dict[str, Any]:
        self._fired.add(tool_id)
        detail = {
            "mode": self.mode,
            "tool_id": tool_id,
            "external_mutation": "SUCCESS",
            "returned_to_one": "SUCCESS",
            "returned_to_agent": "LOST",
            "agent_observation": "AMBIGUOUS",
        }
        self.last_injection = detail
        return detail


class ToolTransportError(Exception):
    """Transient transport failure visible to the agent."""

    def __init__(self, message: str, *, transient: bool = True) -> None:
        super().__init__(message)
        self.transient = transient
        self.message = message

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": "ToolTransportError",
            "message": self.message,
            "transient": self.transient,
            "outcome_unknown": True,
        }
