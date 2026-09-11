"""Unit tests for policy engine (stdlib-friendly)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from repair.runtime.policy_engine import evaluate_policies, vocabulary_guard


def base_ctx(**overrides):
    ctx = {
        "effect_type": "mutation",
        "persistent_side_effect": True,
        "prior_outcome_state": "ambiguous",
        "consequence_level": "high",
        "replay_type": "uncorrelated",
        "prior": {"op_id": "op_abc"},
        "capabilities": {"native_safe_replay": "unavailable", "state_verification": "available"},
        "required_steps_satisfied": [],
    }
    ctx.update(overrides)
    return ctx


OVERBROAD = {
    "id": "ambiguous_side_effect_recovery",
    "version": 2,
    "match": {"effect_type": "mutation", "persistent_side_effect": True},
    "require": ["verify_authoritative_state"],
    "prohibit": ["uncorrelated_replay"],
    "recovery": {
        "if_native_safe_replay_available": ["preserve_operation_identity"],
        "otherwise": ["verify_authoritative_state"],
    },
    "allow": ["correlated_replay"],
    "bypass_when": ["read_only_action"],
}

NARROW = {
    "id": "ambiguous_side_effect_recovery",
    "version": 3,
    "match": {
        "effect_type": "mutation",
        "persistent_side_effect": True,
        "outcome_state": "ambiguous",
    },
    "require": ["establish_safe_replay"],
    "prohibit": ["uncorrelated_replay"],
    "recovery": {
        "if_native_safe_replay_available": ["preserve_operation_identity"],
        "otherwise": ["verify_authoritative_state"],
    },
    "allow": ["correlated_replay", "retry", "continue"],
    "bypass_when": [
        "read_only_action",
        "definitive_precommit_failure",
        "confirmed_failed_mutation",
        "no_prior_operation",
    ],
}


def test_vocabulary_guard_rejects_domain_tokens():
    bad = {**NARROW, "rationale": "Never duplicate a Stripe refund"}
    ok, hits = vocabulary_guard(bad)
    assert not ok
    assert "stripe" in hits or "refund" in hits


def test_vocabulary_guard_accepts_clean_policy():
    ok, hits = vocabulary_guard(NARROW)
    assert ok
    assert hits == []


def test_overbroad_requires_verification_on_success():
    # Case 4: successful mutation follow-up — overbroad still requires verify
    ctx = base_ctx(prior_outcome_state="success", replay_type="none", prior={"op_id": "op_1"})
    d = evaluate_policies([OVERBROAD], ctx)
    assert d["verdict"] == "REQUIRE"
    assert "verify_authoritative_state" in d["required_steps"]


def test_narrow_allows_successful_mutation_continue():
    ctx = base_ctx(prior_outcome_state="success", replay_type="none", prior={"op_id": "op_1"})
    d = evaluate_policies([NARROW], ctx)
    assert d["verdict"] == "ALLOW"


def test_narrow_blocks_uncorrelated_replay_after_ambiguous():
    ctx = base_ctx()
    d = evaluate_policies([NARROW], ctx)
    assert d["verdict"] == "BLOCK"
    assert "verify_authoritative_state" in d["required_steps"]


def test_narrow_allows_read_only_retry():
    ctx = base_ctx(
        effect_type="read",
        persistent_side_effect=False,
        prior_outcome_state="ambiguous",
        replay_type="uncorrelated",
    )
    d = evaluate_policies([NARROW], ctx)
    # Explicit bypass_when or no_match on mutation-only policy → ALLOW
    assert d["verdict"] == "ALLOW"
    assert d["reasons"][0] in {"bypass", "no_matching_policy", "no_match"}


def test_narrow_allows_precommit_failure_retry():
    ctx = base_ctx(
        prior_outcome_state="precommit_failure",
        replay_type="uncorrelated",
    )
    d = evaluate_policies([NARROW], ctx)
    assert d["verdict"] == "ALLOW"


def test_empty_registry_allows():
    d = evaluate_policies([], base_ctx())
    assert d["verdict"] == "ALLOW"


def test_native_replay_branch():
    ctx = base_ctx(capabilities={"native_safe_replay": "available"})
    d = evaluate_policies([NARROW], ctx)
    assert d["verdict"] == "BLOCK"
    assert "preserve_operation_identity" in d["required_steps"]
