"""Bounded support agent — same model/prompt/tools for V1 and V3."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from repair.agent.prompts import BASE_PROMPT_HASH_MATERIAL, BASE_SYSTEM_PROMPT
from repair.config import get_settings
from repair.events.bus import bus
from repair.runtime.fault import ToolTransportError
from repair.runtime.gateway import Gateway


def prompt_hash() -> str:
    return hashlib.sha256(BASE_PROMPT_HASH_MATERIAL.encode()).hexdigest()[:16]


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "stripe_get_order",
            "description": "Read synthetic order validation state",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stripe_create_refund",
            "description": "Create an approved Stripe TEST-mode refund",
            "parameters": {
                "type": "object",
                "properties": {
                    "payment_intent": {"type": "string"},
                    "amount": {"type": "integer"},
                },
                "required": ["payment_intent", "amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "linear_create_issue",
            "description": "Create a Linear engineering escalation issue",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "priority": {"type": "integer"},
                },
                "required": ["title", "description"],
            },
        },
    },
]


class SupportAgent:
    """Tool-calling loop. Tools always go through Gateway.execute — never One directly."""

    def __init__(
        self,
        gateway: Gateway,
        *,
        run_id: str,
        model: str | None = None,
        max_tool_calls: int = 3,
        payment_intent: str | None = None,
    ) -> None:
        self.gateway = gateway
        self.run_id = run_id
        self.settings = get_settings()
        self.model = model or self.settings.repair_support_model
        self.max_tool_calls = max_tool_calls
        self.payment_intent = payment_intent
        self.tool_calls = 0
        self.transcript: list[dict[str, Any]] = []

    def _dispatch_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        self.tool_calls += 1
        if name == "stripe_get_order":
            tool_id, params = "stripe.get_order", dict(args)
        elif name == "stripe_create_refund":
            tool_id, params = (
                "stripe.create_refund",
                {
                    "payment_intent": args.get("payment_intent") or self.payment_intent,
                    "amount": int(args.get("amount", 1290)),
                },
            )
        elif name == "linear_create_issue":
            tool_id, params = (
                "linear.create_issue",
                {
                    "title": args["title"],
                    "description": args.get("description", ""),
                    "priority": int(args.get("priority", 1)),
                },
            )
        else:
            return {"ok": False, "error": f"unknown tool {name}"}
        try:
            return self.gateway.execute(tool_id, params, proposed_by="llm")
        except ToolTransportError as exc:
            return {"ok": False, **exc.to_dict()}

    def run_scripted(
        self,
        *,
        steps: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Deterministic path used when no LLM key / for reliable demo control.

        Still uses the same gateway, tools, fault, and retry instruction semantics:
        after a transient failure, exactly one retry is attempted.
        """
        results: list[dict[str, Any]] = []
        for step in steps:
            name = step["tool"]
            args = dict(step.get("args") or {})
            out = self._dispatch_tool(name, args)
            results.append({"tool": name, "args": args, "result": out})
            transient = bool(out.get("transient")) or out.get("error") == "ToolTransportError"
            if transient and self.tool_calls < self.max_tool_calls:
                # Ordinary retry once — identical rule for V1 and V3
                retry_out = self._dispatch_tool(name, args)
                results.append({"tool": name, "args": args, "result": retry_out, "retry": True})
        return {
            "mode": "scripted",
            "prompt_hash": prompt_hash(),
            "model": self.model,
            "tool_calls": self.tool_calls,
            "results": results,
        }

    def run_llm(self, user_task: str) -> dict[str, Any]:
        """Optional live LLM path via CrewAI/OpenAI tool calling."""
        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY missing — use run_scripted or set the key")

        from openai import OpenAI

        client = OpenAI(api_key=self.settings.openai_api_key)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": BASE_SYSTEM_PROMPT},
            {"role": "user", "content": user_task},
        ]
        bus.emit(self.run_id, "agent.started", {"model": self.model, "prompt_hash": prompt_hash()})

        for _ in range(self.max_tool_calls + 2):
            resp = client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=TOOL_SCHEMAS,
                temperature=0,
            )
            msg = resp.choices[0].message
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in (msg.tool_calls or [])
                    ]
                    or None,
                }
            )
            if not msg.tool_calls:
                return {
                    "mode": "llm",
                    "prompt_hash": prompt_hash(),
                    "model": self.model,
                    "tool_calls": self.tool_calls,
                    "final": msg.content,
                    "messages": messages,
                }
            for tc in msg.tool_calls:
                if self.tool_calls >= self.max_tool_calls:
                    tool_result = {"ok": False, "error": "max_tool_calls exceeded"}
                else:
                    args = json.loads(tc.function.arguments or "{}")
                    tool_result = self._dispatch_tool(tc.function.name, args)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(tool_result)[:8000],
                    }
                )
        return {
            "mode": "llm",
            "prompt_hash": prompt_hash(),
            "model": self.model,
            "tool_calls": self.tool_calls,
            "final": "stopped",
            "messages": messages,
        }
