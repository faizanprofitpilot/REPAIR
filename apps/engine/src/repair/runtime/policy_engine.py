"""Constrained policy DSL evaluator (stdlib-friendly core; also imported by Daytona harness).

This module intentionally avoids non-stdlib imports so it can be uploaded
unchanged into a Daytona sandbox. The Pydantic models live elsewhere; the
harness passes plain dicts.
"""

from __future__ import annotations

from typing import Any


DENYLIST_TOKENS = (
    "stripe",
    "refund",
    "linear",
    "issue",
    "$12.90",
    "$38.90",
    "504",
    "/v1/",
    "payment_intent",
    "issuecreate",
)


def vocabulary_guard(policy: dict[str, Any]) -> tuple[bool, list[str]]:
    """Reject policies containing domain-specific vocabulary."""
    import json

    blob = json.dumps(policy).lower()
    hits = [tok for tok in DENYLIST_TOKENS if tok.lower() in blob]
    # Allow the structural keys themselves; denylist is for free-text fields mostly.
    # Hard reject if domain tokens appear anywhere — matches plan requirement.
    return (len(hits) == 0, hits)


def _match_holds(match: dict[str, Any], ctx: dict[str, Any]) -> bool:
    if not match:
        return True
    for key, expected in match.items():
        if expected is None:
            continue
        actual = ctx.get(key)
        if actual != expected:
            return False
    return True


def _bypass(bypass_when: list[str], ctx: dict[str, Any]) -> bool:
    for condition in bypass_when or []:
        if condition == "read_only_action" and ctx.get("effect_type") == "read":
            return True
        if condition == "definitive_precommit_failure" and ctx.get("prior_outcome_state") == "precommit_failure":
            return True
        if condition == "confirmed_failed_mutation" and ctx.get("prior_outcome_state") == "definitive_failure":
            return True
        if condition == "no_prior_operation" and not ctx.get("prior"):
            return True
    return False


def _resolve_recovery_steps(policy: dict[str, Any], ctx: dict[str, Any]) -> list[str]:
    recovery = policy.get("recovery") or {}
    native = (ctx.get("capabilities") or {}).get("native_safe_replay")
    if native == "available":
        steps = recovery.get("if_native_safe_replay_available") or ["preserve_operation_identity"]
    else:
        steps = recovery.get("otherwise") or ["verify_authoritative_state"]
    return list(steps)


def _concretize_require(require: list[str], policy: dict[str, Any], ctx: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for step in require or []:
        if step == "establish_safe_replay":
            out.extend(_resolve_recovery_steps(policy, ctx))
        else:
            out.append(step)
    # de-dupe preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for s in out:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq


def evaluate_policy(policy: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a single policy against an execution context dict.

    Context keys expected:
      effect_type, persistent_side_effect, outcome_state / prior_outcome_state,
      consequence_level, replay_type, prior, capabilities, required_steps_satisfied
    """
    if _bypass(policy.get("bypass_when") or [], ctx):
        return {
            "verdict": "ALLOW",
            "matched": True,
            "reasons": ["bypass"],
            "required_steps": [],
            "matched_policy_id": policy.get("id"),
            "matched_policy_version": policy.get("version"),
        }

    match = policy.get("match") or {}
    # Matching uses prior_outcome_state as outcome_state when present
    match_ctx = {
        "effect_type": ctx.get("effect_type"),
        "persistent_side_effect": ctx.get("persistent_side_effect"),
        "outcome_state": ctx.get("prior_outcome_state") or ctx.get("outcome_state"),
        "consequence_level": ctx.get("consequence_level"),
        "replay_type": ctx.get("replay_type"),
    }
    if not _match_holds(match, match_ctx):
        return {
            "verdict": "ALLOW",
            "matched": False,
            "reasons": ["no_match"],
            "required_steps": [],
            "matched_policy_id": None,
            "matched_policy_version": None,
        }

    reasons: list[str] = ["matched"]
    required = _concretize_require(policy.get("require") or [], policy, ctx)
    satisfied = set(ctx.get("required_steps_satisfied") or [])
    unsatisfied = [s for s in required if s not in satisfied]

    replay_type = ctx.get("replay_type") or "none"
    prohibit = policy.get("prohibit") or []
    if replay_type == "uncorrelated" and "uncorrelated_replay" in prohibit:
        # Prefer recovery steps; also include any unsatisfied require steps
        steps = _resolve_recovery_steps(policy, ctx)
        for s in unsatisfied:
            if s not in steps:
                steps.append(s)
        return {
            "verdict": "BLOCK",
            "matched": True,
            "reasons": reasons + ["prohibit:uncorrelated_replay"],
            "required_steps": steps,
            "matched_policy_id": policy.get("id"),
            "matched_policy_version": policy.get("version"),
        }

    if unsatisfied:
        return {
            "verdict": "REQUIRE",
            "matched": True,
            "reasons": reasons + [f"require:{s}" for s in unsatisfied],
            "required_steps": unsatisfied,
            "matched_policy_id": policy.get("id"),
            "matched_policy_version": policy.get("version"),
        }

    return {
        "verdict": "ALLOW",
        "matched": True,
        "reasons": reasons + ["requirements_satisfied"],
        "required_steps": [],
        "matched_policy_id": policy.get("id"),
        "matched_policy_version": policy.get("version"),
    }


def evaluate_policies(policies: list[dict[str, Any]], ctx: dict[str, Any]) -> dict[str, Any]:
    """Evaluate active policies; most restrictive verdict wins (BLOCK > REQUIRE > ALLOW)."""
    best = {
        "verdict": "ALLOW",
        "matched": False,
        "reasons": ["no_active_policies"] if not policies else ["no_matching_policy"],
        "required_steps": [],
        "matched_policy_id": None,
        "matched_policy_version": None,
    }
    rank = {"ALLOW": 0, "REQUIRE": 1, "BLOCK": 2}
    for policy in policies:
        decision = evaluate_policy(policy, ctx)
        if decision.get("matched") and rank[decision["verdict"]] >= rank[best["verdict"]]:
            best = decision
        elif decision.get("matched") and best["verdict"] == "ALLOW" and not best.get("matched"):
            best = decision
    return best
