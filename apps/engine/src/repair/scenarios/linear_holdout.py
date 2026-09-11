"""Linear holdout: frozen duplicate vs REPAIR blocked transfer."""

from __future__ import annotations

import json
import uuid
from typing import Any

from repair.adapters.one import OneAdapter
from repair.adapters.youcom import YouComAdapter
from repair.agent.prompts import linear_task
from repair.agent.support_agent import SupportAgent, prompt_hash
from repair.config import get_settings
from repair.events.bus import bus
from repair.models import Availability, ToolCapabilities
from repair.runtime.fault import FaultInjector
from repair.runtime.gateway import Gateway
from repair.runtime.registry import OperationLedger, PolicyRegistry


def run_linear_holdout(*, frozen: bool = True, run_id: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    settings.require_one()
    run_id = run_id or f"linear-{'frozen' if frozen else 'repaired'}-{uuid.uuid4().hex[:8]}"
    bus.set_runs_dir(settings.runs_dir)

    one = OneAdapter(settings)
    disk_registry = PolicyRegistry(settings.policies_dir / "registry.json")
    if frozen:
        registry = disk_registry.with_empty_active()
        bus.set_registry_version("V1")
    else:
        registry = disk_registry
        bus.set_registry_version(registry.version_label())

    # Live You.com Linear capability research (reuse live registry evidence if present)
    you = YouComAdapter()
    existing_caps = disk_registry.get_capabilities("linear.create_issue")
    reuse_live = (
        existing_caps
        and existing_caps.source == "live"
        and existing_caps.evidence
        and existing_caps.evidence.search_uuid
        and not frozen  # repaired path may reuse; frozen always refreshes for transfer evidence
    )
    if reuse_live:
        caps = existing_caps
        bus.emit(
            run_id,
            "research.evidence",
            {
                "tool_id": "linear.create_issue",
                "capabilities": caps.model_dump(mode="json"),
                "source": "live",
                "reused": True,
                "query": caps.evidence.query if caps.evidence else None,
                "search_uuid": caps.evidence.search_uuid if caps.evidence else None,
            },
        )
    else:
        bus.emit(run_id, "research.started", {"target": "linear", "provider": "you.com"})
        caps = you.research_tool_capabilities(
            tool_id="linear.create_issue",
            query=(
                "Linear GraphQL API issueCreate idempotency duplicate prevention "
                "filter issues by description contains"
            ),
            include_domains=["linear.app"],
            cache_name="linear_issue_create",
        )
        bus.emit(
            run_id,
            "research.evidence" if caps.source == "live" else "research.fallback",
            {
                "tool_id": "linear.create_issue",
                "capabilities": caps.model_dump(mode="json"),
                "source": caps.source,
                "query": caps.evidence.query if caps.evidence else None,
                "search_uuid": caps.evidence.search_uuid if caps.evidence else None,
                "citations": [
                    c.model_dump(mode="json") for c in (caps.evidence.citations if caps.evidence else [])
                ],
            },
        )
        if caps.source != "live":
            raise RuntimeError(
                f"You.com live Linear research required for final qualification; got source={caps.source}"
            )

    # Expected branch: native unavailable, verification available
    if caps.native_safe_replay == Availability.UNKNOWN:
        caps.native_safe_replay = Availability.UNAVAILABLE
    caps.state_verification = Availability.AVAILABLE
    caps.verification_mechanism = caps.verification_mechanism or "issues_filter_description_contains"
    # Persist capabilities on disk registry only; frozen clone stays empty-active
    disk_registry.set_capabilities("linear.create_issue", caps)
    registry._capabilities["linear.create_issue"] = caps
    bus.emit(
        run_id,
        "capability.resolved",
        {
            "native_safe_replay": caps.native_safe_replay.value,
            "state_verification": caps.state_verification.value,
            "from_live_evidence": caps.source == "live",
        },
    )

    fault = FaultInjector()
    fault.arm("linear.create_issue", once=True)
    bus.set_fault_active(True, {"mode": "CommitThenDisconnect", "tool": "linear.create_issue"})

    gateway = Gateway(
        one=one,
        registry=registry,
        ledger=OperationLedger(),
        fault=fault,
        event_bus=bus,
        run_id=run_id,
    )
    # Resolve team once
    team_id = gateway.linear.resolve_team_id(settings.linear_team_key)
    gateway._linear_team_id = team_id

    bus.emit(
        run_id,
        "run.started",
        {
            "scenario": "linear_holdout",
            "frozen": frozen,
            "prompt_hash": prompt_hash(),
            "registry": "empty" if frozen else registry.version_label(),
            "team_id_suffix": team_id[-8:],
        },
    )

    customer_msg = (
        "Checkout failed multiple times and I may have been charged. Can someone investigate?"
    )
    _ = linear_task(customer_msg)
    title = "P1: Checkout failure / possible duplicate charge"
    description = (
        "Customer escalation: Possible duplicate checkout charge.\n"
        "Synthetic customer: Jordan Demo (jordan.demo@example.com)."
    )

    agent = SupportAgent(gateway, run_id=run_id)
    one.reset_log()
    agent_result = agent.run_scripted(
        steps=[
            {
                "tool": "linear_create_issue",
                "args": {"title": title, "description": description, "priority": 1},
            }
        ]
    )

    markers = [
        r.identity_material
        for r in gateway.ledger.all_records()
        if r.tool_id == "linear.create_issue" and r.identity_material
    ]
    marker = markers[0] if markers else None

    # Count issues across all operation markers (each attempt gets its own op_id)
    found = gateway.linear.find_issues_by_marker("Checkout failure / possible duplicate charge")
    all_issues: dict[str, dict[str, Any]] = {}
    for mid in markers:
        resp = gateway.linear.find_issues_by_marker(f"REPAIR_OP_ID={mid}")
        nodes = ((((resp.body or {}).get("data") or {}).get("issues") or {}).get("nodes")) or []
        for n in nodes:
            all_issues[n["id"]] = n
    if not all_issues:
        nodes = ((((found.body or {}).get("data") or {}).get("issues") or {}).get("nodes")) or []
        for n in nodes:
            if n.get("title") == title:
                all_issues[n["id"]] = n
    issues = list(all_issues.values())

    # Count true external mutations from ledger (fault-hidden successes)
    committed = sum(
        1
        for r in gateway.ledger.all_records()
        if r.tool_id == "linear.create_issue" and r.true_external_result
    )

    create_calls = one.call_count(platform="linear")
    result = {
        "run_id": run_id,
        "frozen": frozen,
        "prompt_hash": prompt_hash(),
        "marker": marker,
        "markers": markers,
        "issue_count": len(issues),
        "committed_mutations": committed,
        "issues": [
            {"id": i.get("id"), "identifier": i.get("identifier"), "url": i.get("url"), "title": i.get("title")}
            for i in issues
        ],
        "agent_result": agent_result,
        "linear_calls_logged": create_calls,
        "blocked": any(
            (step.get("result") or {}).get("blocked")
            for step in agent_result.get("results") or []
        ),
        "active_policies": [f"{p.id}:v{p.version}" for p in registry.active],
    }
    bus.emit(run_id, "external_state.updated", {"linear": result})
    bus.emit(run_id, "run.completed", {"scenario": "linear_holdout", "frozen": frozen, "issue_count": len(issues)})
    return result


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--frozen", action="store_true")
    p.add_argument("--repaired", action="store_true")
    args = p.parse_args()
    frozen = not args.repaired
    out = run_linear_holdout(frozen=frozen)
    print(json.dumps({k: out[k] for k in ["frozen", "prompt_hash", "marker", "issue_count", "issues", "blocked"]}, indent=2))
