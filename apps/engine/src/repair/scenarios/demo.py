"""Full demo orchestrator: Stripe incident → learn → Linear holdout transfer."""

from __future__ import annotations

import json
import traceback
import uuid
from typing import Any

from repair.agent.support_agent import prompt_hash
from repair.config import get_settings
from repair.events.bus import bus
from repair.flow.repair_flow import run_crewai_flow
from repair.scenarios.linear_holdout import run_linear_holdout
from repair.scenarios.stripe_incident import run_stripe_incident


def run_demo(
    *,
    run_id: str | None = None,
    phases: list[str] | None = None,
    skip_learning_if_promoted: bool = True,
) -> dict[str, Any]:
    """
    Run the end-to-end demo under one run_id so SSE clients see a continuous chain.

    Default phases:
      stripe_frozen → learn → linear_frozen → linear_repaired
    """
    settings = get_settings()
    settings.require_one()
    run_id = run_id or f"demo-{uuid.uuid4().hex[:10]}"
    bus.set_runs_dir(settings.runs_dir)
    bus.update_state(phase="starting", demo_run_id=run_id)
    bus.set_fault_active(False)

    selected = phases or [
        "stripe_frozen",
        "learn",
        "linear_frozen",
        "linear_repaired",
    ]

    bus.emit(
        run_id,
        "run.started",
        {
            "scenario": "full_demo",
            "phases": selected,
            "prompt_hash": prompt_hash(),
        },
    )

    results: dict[str, Any] = {"run_id": run_id, "prompt_hash": prompt_hash(), "phases": {}}
    errors: list[dict[str, str]] = []

    try:
        if "stripe_frozen" in selected:
            bus.update_state(phase="stripe_frozen", registry_version="V1")
            bus.set_registry_version("V1")
            out = run_stripe_incident(frozen=True, run_id=run_id)
            incident = out.get("incident") or out
            results["phases"]["stripe_frozen"] = {
                "refund_count": incident.get("refund_count"),
                "total_refunded": incident.get("refunded_cents"),
                "payment_intent": incident.get("payment_intent") or out.get("payment_intent"),
            }
            bus.update_state(stripe=results["phases"]["stripe_frozen"])

        if "learn" in selected:
            bus.update_state(phase="learn")
            # Final qualification always re-runs the learning loop through CrewAI Flow
            # so promotion evidence is live (You.com + Daytona), not a prior handoff.
            fixture_path = settings.fixtures_dir / "incident_stripe.json"
            existing = json.loads(fixture_path.read_text()) if fixture_path.exists() else None
            # If stripe_frozen just ran, reuse its fixture to avoid a third refund pair
            # unless force-learn without prior stripe phase and no fixture.
            out = run_crewai_flow(
                run_id=run_id,
                skip_live_incident=bool(existing) or "stripe_frozen" in selected,
                existing_fixture=existing,
            )
            results["phases"]["learn"] = {
                "promoted": bool(out.get("promoted")),
                "eval_count": len(out.get("eval_results") or []),
                "flow_engine": out.get("flow_engine"),
                "promoted_version": (out.get("promoted") or {}).get("version")
                if isinstance(out.get("promoted"), dict)
                else None,
            }

        if "linear_frozen" in selected:
            bus.update_state(phase="linear_frozen")
            out = run_linear_holdout(frozen=True, run_id=run_id)
            results["phases"]["linear_frozen"] = {
                "issue_count": out.get("issue_count"),
                "issues": out.get("issues"),
                "blocked": out.get("blocked"),
                "prompt_hash": out.get("prompt_hash"),
            }
            bus.update_state(linear_frozen=results["phases"]["linear_frozen"])

        if "linear_repaired" in selected:
            bus.update_state(phase="linear_repaired")
            out = run_linear_holdout(frozen=False, run_id=run_id)
            results["phases"]["linear_repaired"] = {
                "issue_count": out.get("issue_count"),
                "issues": out.get("issues"),
                "blocked": out.get("blocked"),
                "prompt_hash": out.get("prompt_hash"),
            }
            bus.update_state(linear_repaired=results["phases"]["linear_repaired"])

        bus.update_state(phase="completed")
        bus.emit(run_id, "run.completed", {"scenario": "full_demo", "ok": True, "results": results["phases"]})
        results["ok"] = True
    except Exception as e:
        errors.append({"error": str(e), "trace": traceback.format_exc()[-2000:]})
        bus.emit(run_id, "run.failed", {"error": str(e)})
        bus.update_state(phase="failed", last_error=str(e))
        results["ok"] = False
        results["errors"] = errors
    finally:
        bus.close_run(run_id)

    return results


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--phases", default="", help="comma list: stripe_frozen,learn,linear_frozen,linear_repaired")
    p.add_argument("--force-learn", action="store_true")
    args = p.parse_args()
    phases = [x.strip() for x in args.phases.split(",") if x.strip()] or None
    out = run_demo(phases=phases, skip_learning_if_promoted=not args.force_learn)
    print(json.dumps({k: out[k] for k in out if k != "errors"}, indent=2, default=str))
