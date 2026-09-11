"""Frozen / repaired Stripe incident scenarios."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from repair.adapters.one import OneAdapter
from repair.adapters.stripe_tool import StripeTool
from repair.agent.prompts import refund_task
from repair.agent.support_agent import SupportAgent, prompt_hash
from repair.config import REPO_ROOT, get_settings
from repair.events.bus import bus
from repair.runtime.fault import FaultInjector
from repair.runtime.gateway import Gateway
from repair.runtime.registry import OperationLedger, PolicyRegistry


def _load_orders() -> dict[str, Any]:
    path = REPO_ROOT / "fixtures" / "customers.json"
    data = json.loads(path.read_text())
    return data.get("orders") or {}


def run_stripe_incident(*, frozen: bool = True, run_id: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    settings.require_one()
    run_id = run_id or f"stripe-{'frozen' if frozen else 'repaired'}-{uuid.uuid4().hex[:8]}"
    bus.set_runs_dir(settings.runs_dir)
    bus.set_registry_version("V1" if frozen else "V3")

    one = OneAdapter(settings)
    stripe = StripeTool(one)
    stripe.assert_test_mode()

    # Seed real TEST payment
    pi = stripe.seed_payment_intent(amount=3890, metadata={"repair": "incident", "run": run_id})
    if not pi.ok:
        raise RuntimeError(f"Failed to seed payment intent: {pi.error} {pi.body}")
    payment_intent = (pi.body or {}).get("id")

    disk_registry = PolicyRegistry(settings.policies_dir / "registry.json")
    if frozen:
        # Control: empty active policies in-memory only (never persist empty active set)
        registry = disk_registry.with_empty_active()
    else:
        registry = disk_registry
    bus.set_registry_version(registry.version_label() if not frozen else "V1")

    # Load Stripe capability from preflight if present
    idem_path = settings.fixtures_dir / "preflight" / "stripe_idempotency.json"
    if idem_path.exists():
        idem = json.loads(idem_path.read_text())
        from repair.models import Availability, ToolCapabilities

        caps = ToolCapabilities(
            tool_id="stripe.create_refund",
            native_safe_replay=Availability.AVAILABLE
            if idem.get("header_passthrough_ok")
            else Availability.UNAVAILABLE,
            mechanism="idempotency_key" if idem.get("header_passthrough_ok") else None,
            preserve_operation_identity_required=bool(idem.get("header_passthrough_ok")),
            state_verification=Availability.AVAILABLE,
            verification_mechanism="list_refunds",
            preflight_result=idem,
            source="preflight",
        )
        registry.set_capabilities("stripe.create_refund", caps)

    fault = FaultInjector()
    fault.arm("stripe.create_refund", once=True)
    bus.set_fault_active(True, {"mode": "CommitThenDisconnect", "tool": "stripe.create_refund"})

    gateway = Gateway(
        one=one,
        registry=registry,
        ledger=OperationLedger(),
        fault=fault,
        event_bus=bus,
        run_id=run_id,
        synthetic_orders=_load_orders(),
    )

    bus.emit(
        run_id,
        "run.started",
        {
            "scenario": "stripe_incident",
            "frozen": frozen,
            "prompt_hash": prompt_hash(),
            "payment_intent": payment_intent,
            "registry": "empty" if frozen else registry.version_label(),
        },
    )

    agent = SupportAgent(gateway, run_id=run_id, payment_intent=payment_intent)
    # Scripted steps mirror the shared retry instruction (deterministic demo).
    # Same steps for V1 and V3 — only the registry differs.
    customer_msg = (
        "Part of my order arrived damaged. Support approved a $12.90 partial refund "
        "and said I can keep the item. Can you process that?"
    )
    _ = refund_task(customer_msg)
    agent_result = agent.run_scripted(
        steps=[
            {"tool": "stripe_get_order", "args": {"order_id": "ord_demo_001"}},
            {
                "tool": "stripe_create_refund",
                "args": {"payment_intent": payment_intent, "amount": 1290},
            },
        ]
    )

    listed = stripe.list_refunds(payment_intent)
    refunds = (listed.body or {}).get("data") or []
    total = sum(int(r.get("amount") or 0) for r in refunds)
    authorized = 1290
    incident = {
        "authorized_cents": authorized,
        "refunded_cents": total,
        "refund_count": len(refunds),
        "refund_ids": [r.get("id") for r in refunds],
        "over_refund_cents": max(0, total - authorized),
        "payment_intent": payment_intent,
    }
    if len(refunds) >= 2 and frozen:
        bus.emit(run_id, "incident.detected", incident)
    elif len(refunds) <= 1 and not frozen:
        bus.emit(run_id, "incident.prevented", incident)
    else:
        bus.emit(run_id, "incident.detected" if total > authorized else "external_state.updated", incident)

    bus.emit(run_id, "external_state.updated", {"stripe": incident})
    bus.emit(run_id, "run.completed", {"scenario": "stripe_incident", "frozen": frozen})

    # Persist fixture for Daytona when frozen incident produces duplicates
    fixture = {
        "run_id": run_id,
        "payment_intent": payment_intent,
        "agent_result": agent_result,
        "incident": incident,
        "prompt_hash": prompt_hash(),
        "frozen": frozen,
        "ledger": [r.model_dump(mode="json") for r in gateway.ledger.all_records()],
        "starting_state": {
            "order_total_cents": 3890,
            "approved_refund_cents": 1290,
            "already_refunded_cents": 0,
        },
        "tool_metadata": registry.tool_meta("stripe.create_refund").model_dump(mode="json"),
        "capabilities_at_time": registry.get_capabilities("stripe.create_refund").model_dump(mode="json"),
        "outcome_classification": "ambiguous_then_uncorrelated_replay"
        if frozen and len(refunds) >= 2
        else "repaired_or_single",
        "proposed_follow_up": "create_refund_retry",
        "final_consequence": {
            "authorized": authorized,
            "refunded": total,
        },
    }
    if frozen:
        dest = settings.fixtures_dir / "incident_stripe.json"
        dest.write_text(json.dumps(fixture, indent=2, default=str))
        fixture["fixture_path"] = str(dest)

    return fixture


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--frozen", action="store_true", default=True)
    p.add_argument("--repaired", action="store_true")
    args = p.parse_args()
    frozen = not args.repaired
    result = run_stripe_incident(frozen=frozen)
    print(json.dumps({"refund_count": result["incident"]["refund_count"], "refunded": result["incident"]["refunded_cents"], "ids": result["incident"]["refund_ids"], "prompt_hash": result["prompt_hash"]}, indent=2))
