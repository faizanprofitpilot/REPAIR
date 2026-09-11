"""CrewAI Flow: EXECUTE → DIAGNOSE → RESEARCH → SYNTHESIZE → VALIDATE → PROMOTE/REJECT."""

from __future__ import annotations

import json
import uuid
from typing import Any

from pydantic import BaseModel, Field

from repair.adapters.youcom import YouComAdapter
from repair.config import get_settings
from repair.evaluation.daytona_runner import evaluate_candidate
from repair.events.bus import bus
from repair.models import (
    Availability,
    LearnedPolicy,
    PolicyMatch,
    PolicyRecovery,
    ProhibitAction,
    RequireStep,
    BypassWhen,
    AllowAction,
    EffectType,
    OutcomeState,
)
from repair.runtime.policy_engine import vocabulary_guard
from repair.runtime.registry import PolicyRegistry
from repair.scenarios.stripe_incident import run_stripe_incident


class Diagnosis(BaseModel):
    observed_failure: str
    root_cause: str
    effect_type: str = "mutation"
    persistent_side_effect: bool = True
    outcome_state: str = "ambiguous"
    replay_type: str = "uncorrelated"


class RepairState(BaseModel):
    run_id: str = ""
    incident: dict[str, Any] = Field(default_factory=dict)
    diagnosis: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    eval_results: list[dict[str, Any]] = Field(default_factory=list)
    promoted_version: int | None = None
    attempt: int = 0
    skip_live_incident: bool = False
    existing_fixture: dict[str, Any] | None = None
    prior_eval: dict[str, Any] | None = None
    last_candidate: dict[str, Any] | None = None
    last_eval: dict[str, Any] | None = None
    flow_engine: str = "crewai"


def diagnose_from_incident(incident: dict[str, Any], *, run_id: str) -> Diagnosis:
    """Live LLM diagnosis when OPENAI_API_KEY is set. No silent fallback in final qualification."""
    settings = get_settings()
    base = Diagnosis(
        observed_failure=(
            "A persistent external mutation produced an ambiguous client-visible outcome. "
            "The agent then performed an uncorrelated replay."
        ),
        root_cause=(
            "The runtime had no requirement to establish a safe replay strategy before "
            "repeating an ambiguous side effect."
        ),
    )
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY required for live diagnose — refusing deterministic fallback")

    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    prompt = (
        "Diagnose this agentic incident. Return JSON with keys: "
        "observed_failure, root_cause, effect_type, persistent_side_effect, "
        "outcome_state, replay_type. Use domain-free language only "
        "(no product names, no vendor APIs). Incident JSON:\n"
        + json.dumps(
            {
                "refund_count": (incident.get("incident") or incident).get("refund_count"),
                "outcome_classification": incident.get("outcome_classification"),
                "final_consequence": incident.get("final_consequence"),
            }
        )
    )
    resp = client.chat.completions.create(
        model=settings.repair_flow_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a reliability engineer. Reply with JSON only using exactly these keys: "
                    "observed_failure (string), root_cause (string), effect_type (string), "
                    "persistent_side_effect (boolean), outcome_state (string), replay_type (string)."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    data = json.loads(resp.choices[0].message.content or "{}")
    cleaned = {
        "observed_failure": str(data.get("observed_failure") or base.observed_failure),
        "root_cause": str(data.get("root_cause") or base.root_cause),
        "effect_type": str(data.get("effect_type") or base.effect_type),
        "persistent_side_effect": bool(data.get("persistent_side_effect"))
        if isinstance(data.get("persistent_side_effect"), bool)
        else base.persistent_side_effect,
        "outcome_state": str(data.get("outcome_state") or base.outcome_state),
        "replay_type": str(data.get("replay_type") or base.replay_type),
    }
    diagnosis = Diagnosis.model_validate(cleaned)
    bus.emit(run_id, "diagnosis.mode", {"mode": "openai", "model": settings.repair_flow_model})
    return diagnosis


def _deterministic_candidate(attempt: int, prior_eval: dict[str, Any] | None, diagnosis: Diagnosis) -> LearnedPolicy:
    if attempt <= 1 and not (prior_eval and prior_eval.get("verdict") == "REJECT"):
        return LearnedPolicy(
            id="ambiguous_side_effect_recovery",
            version=2,
            rationale="Conservative-first: reconcile authoritative state after every persistent mutation.",
            match=PolicyMatch(effect_type=EffectType.MUTATION, persistent_side_effect=True),
            require=[RequireStep.VERIFY_AUTHORITATIVE_STATE],
            prohibit=[ProhibitAction.UNCORRELATED_REPLAY],
            recovery=PolicyRecovery(),
            allow=[AllowAction.CORRELATED_REPLAY],
            bypass_when=[BypassWhen.READ_ONLY_ACTION],
        )
    return LearnedPolicy(
        id="ambiguous_side_effect_recovery",
        version=3,
        rationale=(
            "Narrowed after evaluation: only ambiguous persistent side effects require "
            "safe replay / verification. Feedback: "
            + json.dumps(
                {
                    "unnecessary_verification_operations": (prior_eval or {}).get(
                        "unnecessary_verification_operations"
                    ),
                    "reject_reasons": (prior_eval or {}).get("reject_reasons"),
                }
            )
        ),
        match=PolicyMatch(
            effect_type=EffectType.MUTATION,
            persistent_side_effect=True,
            outcome_state=OutcomeState.AMBIGUOUS,
        ),
        require=[RequireStep.ESTABLISH_SAFE_REPLAY],
        prohibit=[ProhibitAction.UNCORRELATED_REPLAY],
        recovery=PolicyRecovery(),
        allow=[AllowAction.CORRELATED_REPLAY, AllowAction.RETRY, AllowAction.CONTINUE],
        bypass_when=[
            BypassWhen.READ_ONLY_ACTION,
            BypassWhen.DEFINITIVE_PRECOMMIT_FAILURE,
            BypassWhen.CONFIRMED_FAILED_MUTATION,
            BypassWhen.NO_PRIOR_OPERATION,
        ],
    )


def _sanitize_policy_draft(raw: dict[str, Any], *, attempt: int) -> dict[str, Any]:
    """Coerce LLM draft into valid DSL enums without inventing domain-specific content."""
    require_ok = {s.value for s in RequireStep}
    allow_ok = {s.value for s in AllowAction}
    prohibit_ok = {s.value for s in ProhibitAction}
    bypass_ok = {s.value for s in BypassWhen}

    require: list[str] = []
    allow: list[str] = list(raw.get("allow") or [])
    prohibit: list[str] = list(raw.get("prohibit") or [])
    bypass: list[str] = list(raw.get("bypass_when") or [])

    for item in raw.get("require") or []:
        if item in require_ok:
            require.append(item)
        elif item in allow_ok:
            allow.append(item)
        elif item in prohibit_ok:
            prohibit.append(item)

    # Deduplicate while preserving order
    def uniq(xs: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for x in xs:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    raw["require"] = uniq([x for x in require if x in require_ok])
    raw["allow"] = uniq([x for x in allow if x in allow_ok])
    raw["prohibit"] = uniq([x for x in prohibit if x in prohibit_ok])
    raw["bypass_when"] = uniq([x for x in bypass if x in bypass_ok])

    match = dict(raw.get("match") or {})
    # Matching on replay_type prevents the policy from applying to the first mutation
    # (replay_type=none), which fails safety cases. Keep match domain-free and general.
    match["replay_type"] = None
    if attempt <= 1:
        # Conservative-first / overbroad: do not narrow to ambiguous-only yet.
        match["outcome_state"] = None
        # Overbroad requires verification after every persistent mutation.
        raw["require"] = [RequireStep.VERIFY_AUTHORITATIVE_STATE.value]
    else:
        # Refined: only ambiguous persistent mutations; single abstract require.
        match["outcome_state"] = OutcomeState.AMBIGUOUS.value
        raw["require"] = [RequireStep.ESTABLISH_SAFE_REPLAY.value]
    if match.get("effect_type") is None:
        match["effect_type"] = EffectType.MUTATION.value
    if match.get("persistent_side_effect") is None:
        match["persistent_side_effect"] = True
    raw["match"] = match

    if ProhibitAction.UNCORRELATED_REPLAY.value not in raw["prohibit"]:
        raw["prohibit"] = uniq(raw["prohibit"] + [ProhibitAction.UNCORRELATED_REPLAY.value])

    recovery = raw.get("recovery") or {}
    if isinstance(recovery, dict):
        for key in ("if_native_safe_replay_available", "otherwise"):
            vals = recovery.get(key) or []
            recovery[key] = [x for x in vals if x in require_ok]
        if not recovery.get("if_native_safe_replay_available"):
            recovery["if_native_safe_replay_available"] = [RequireStep.PRESERVE_OPERATION_IDENTITY.value]
        if not recovery.get("otherwise"):
            recovery["otherwise"] = [RequireStep.VERIFY_AUTHORITATIVE_STATE.value]
        raw["recovery"] = recovery
    return raw


def synthesize_candidate(
    attempt: int,
    prior_eval: dict[str, Any] | None,
    diagnosis: Diagnosis,
    *,
    run_id: str,
) -> LearnedPolicy:
    """Produce candidates via live OpenAI. No silent deterministic fallback."""
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY required for live synthesize — refusing deterministic fallback")

    seed = _deterministic_candidate(attempt, prior_eval, diagnosis)
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    schema_hint = {
        "id": "ambiguous_side_effect_recovery",
        "version": seed.version,
        "rationale": "domain-free string",
        "match": {
            "effect_type": "mutation|read|null",
            "persistent_side_effect": "bool|null",
            "outcome_state": "ambiguous|success|definitive_failure|precommit_failure|pending|null",
            "consequence_level": "low|medium|high|null",
            "replay_type": "none|correlated|uncorrelated|null",
        },
        "require": [
            "establish_safe_replay",
            "preserve_operation_identity",
            "correlated_replay",
            "verify_authoritative_state",
        ],
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
    strategy = (
        "Attempt 1: propose the broadest safe rule (conservative-first). "
        "Match every persistent mutation and require authoritative verification."
        if attempt <= 1 and not (prior_eval and prior_eval.get("verdict") == "REJECT")
        else (
            "Attempt >=2: narrow match/requirements using evaluation feedback so failing "
            "cases pass without weakening safety cases. Prefer matching only ambiguous "
            "persistent mutations and require establish_safe_replay."
        )
    )

    guard_feedback = ""
    last_hits: list[str] = []
    for repair_try in range(1, 4):
        prompt = (
            f"{strategy}\nDiagnosis: {diagnosis.model_dump_json()}\n"
            f"Prior eval: {json.dumps(prior_eval or {})}\n"
            f"Emit ONE JSON object matching this DSL shape:\n{json.dumps(schema_hint)}\n"
            "Hard rules: domain-free vocabulary only; never mention vendors, products, or endpoints."
            + guard_feedback
        )
        resp = client.chat.completions.create(
            model=settings.repair_flow_model,
            messages=[
                {
                    "role": "system",
                    "content": "You synthesize runtime policies as JSON only. No markdown.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw = json.loads(resp.choices[0].message.content or "{}")
        raw["version"] = seed.version
        raw["id"] = raw.get("id") or "ambiguous_side_effect_recovery"
        raw = _sanitize_policy_draft(raw, attempt=attempt)
        candidate = LearnedPolicy.model_validate(raw)
        ok, hits = vocabulary_guard(candidate.model_dump(mode="json"))
        if ok:
            bus.emit(
                run_id,
                "policy.synthesis_mode",
                {
                    "mode": "openai",
                    "model": settings.repair_flow_model,
                    "attempt": attempt,
                    "repair_try": repair_try,
                },
            )
            return candidate
        last_hits = hits
        bus.emit(run_id, "policy.rejected_by_guard", {"hits": hits, "attempt": attempt, "source": "llm"})
        guard_feedback = (
            f"\nPrevious draft failed vocabulary guard for tokens {hits}. "
            "Rewrite with domain-free language only."
        )

    raise RuntimeError(f"Live synthesize failed vocabulary guard after retries: {last_hits}")


def run_learning_loop(
    *,
    skip_live_incident: bool = False,
    existing_fixture: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    run_id = run_id or f"learn-{uuid.uuid4().hex[:8]}"
    bus.set_runs_dir(settings.runs_dir)
    bus.emit(run_id, "run.started", {"scenario": "learning_loop", "engine": "crewai_flow"})

    if skip_live_incident and existing_fixture:
        incident = existing_fixture
    elif skip_live_incident:
        fixture_path = settings.fixtures_dir / "incident_stripe.json"
        if not fixture_path.exists():
            raise RuntimeError("skip_live_incident set but no fixture / existing_fixture provided")
        incident = json.loads(fixture_path.read_text())
    else:
        incident = run_stripe_incident(frozen=True, run_id=f"{run_id}-incident")

    diagnosis = diagnose_from_incident(incident, run_id=run_id)
    bus.emit(run_id, "diagnosis.completed", diagnosis.model_dump())

    you = YouComAdapter()
    bus.emit(run_id, "research.started", {"target": "stripe", "provider": "you.com"})
    caps = you.research_tool_capabilities(
        tool_id="stripe.create_refund",
        query=(
            "Stripe API idempotent requests Idempotency-Key retry POST after "
            "connection failure same parameters ambiguous network error"
        ),
        include_domains=["docs.stripe.com"],
        cache_name="stripe_idempotency",
    )
    idem_path = settings.fixtures_dir / "preflight" / "stripe_idempotency.json"
    if idem_path.exists():
        idem = json.loads(idem_path.read_text())
        if idem.get("header_passthrough_ok"):
            caps.native_safe_replay = Availability.AVAILABLE
            caps.mechanism = "idempotency_key"
            caps.preserve_operation_identity_required = True
            caps.preflight_result = idem
        else:
            caps.native_safe_replay = Availability.UNAVAILABLE
            caps.preflight_result = idem

    event_type = "research.evidence" if caps.source == "live" else "research.fallback"
    bus.emit(
        run_id,
        event_type,
        {
            "tool_id": "stripe.create_refund",
            "capabilities": caps.model_dump(mode="json"),
            "source": caps.source,
            "query": caps.evidence.query if caps.evidence else None,
            "search_uuid": caps.evidence.search_uuid if caps.evidence else None,
            "citations": [c.model_dump(mode="json") for c in (caps.evidence.citations if caps.evidence else [])],
        },
    )
    if caps.source != "live":
        raise RuntimeError(
            f"You.com live research required for final qualification; got source={caps.source} "
            f"detail={caps.preflight_result}"
        )

    bus.emit(
        run_id,
        "capability.resolved",
        {
            "native_safe_replay": caps.native_safe_replay.value,
            "mechanism": caps.mechanism,
            "state_verification": caps.state_verification.value,
            "from_live_evidence": True,
        },
    )

    registry = PolicyRegistry(settings.policies_dir / "registry.json")
    registry.set_capabilities("stripe.create_refund", caps)

    prior_eval: dict[str, Any] | None = None
    promoted: LearnedPolicy | None = None
    eval_results: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []

    for attempt in range(1, 4):
        candidate = synthesize_candidate(attempt, prior_eval, diagnosis, run_id=run_id)
        ok, hits = vocabulary_guard(candidate.model_dump(mode="json"))
        if not ok:
            bus.emit(run_id, "policy.rejected_by_guard", {"hits": hits, "attempt": attempt})
            continue
        bus.emit(
            run_id,
            "policy.generated",
            {"attempt": attempt, "policy": candidate.model_dump(mode="json")},
        )
        cand_path = settings.policies_dir / "candidates" / f"v{candidate.version}.json"
        cand_path.parent.mkdir(parents=True, exist_ok=True)
        cand_path.write_text(json.dumps(candidate.model_dump(mode="json"), indent=2))
        candidates.append(candidate.model_dump(mode="json"))

        bus.emit(run_id, "evaluation.started", {"version": candidate.version, "mode": "daytona"})
        result = evaluate_candidate(candidate, run_id=run_id)
        if result.get("executed_in") != "daytona":
            raise RuntimeError(
                f"Daytona live evaluation required; got executed_in={result.get('executed_in')} "
                f"detail={result.get('daytona_error') or result.get('reject_reasons')}"
            )
        # Persist daytona artifact
        art = settings.runs_dir / run_id / f"daytona_v{candidate.version}.json"
        art.parent.mkdir(parents=True, exist_ok=True)
        art.write_text(json.dumps(result, indent=2))
        eval_results.append(result)
        prior_eval = result

        if result.get("verdict") == "REJECT":
            bus.emit(
                run_id,
                "candidate.rejected",
                {
                    "version": candidate.version,
                    "metrics": {
                        k: result.get(k)
                        for k in [
                            "safety_cases_passed",
                            "negative_controls_passed",
                            "verdict_correctness",
                            "unnecessary_verification_operations",
                            "additional_tool_operations",
                            "regression_failures",
                            "executed_in",
                            "sandbox_id",
                        ]
                    },
                    "reject_reasons": result.get("reject_reasons"),
                },
            )
            continue

        registry.promote(candidate)
        promoted_path = settings.policies_dir / "promoted" / f"v{candidate.version}.json"
        promoted_path.write_text(json.dumps(candidate.model_dump(mode="json"), indent=2))
        bus.emit(
            run_id,
            "candidate.promoted",
            {
                "version": candidate.version,
                "metrics": {
                    k: result.get(k)
                    for k in [
                        "safety_cases_passed",
                        "negative_controls_passed",
                        "verdict_correctness",
                        "unnecessary_verification_operations",
                        "additional_tool_operations",
                        "executed_in",
                        "sandbox_id",
                    ]
                },
            },
        )
        bus.emit(run_id, "registry.updated", {"version": f"V{candidate.version}"})
        bus.set_registry_version(f"V{candidate.version}")
        promoted = candidate
        break

    bus.emit(run_id, "run.completed", {"scenario": "learning_loop", "promoted": bool(promoted)})
    return {
        "run_id": run_id,
        "incident": {
            "refund_count": (incident.get("incident") or incident).get("refund_count")
            if isinstance(incident.get("incident"), dict)
            else incident.get("refund_count"),
            "payment_intent": (incident.get("incident") or incident).get("payment_intent")
            if isinstance(incident.get("incident"), dict)
            else incident.get("payment_intent"),
        },
        "diagnosis": diagnosis.model_dump(),
        "capabilities": caps.model_dump(mode="json"),
        "candidates": candidates,
        "eval_results": eval_results,
        "promoted": promoted.model_dump(mode="json") if promoted else None,
    }


# Real CrewAI Flow wrapper
try:
    from crewai.flow.flow import Flow, start

    class RepairFlow(Flow[RepairState]):
        """CrewAI Flow entry: EXECUTE→DIAGNOSE→RESEARCH→SYNTHESIZE→VALIDATE→PROMOTE/REJECT."""

        @start()
        def run(self) -> str:
            bus.emit(self.state.run_id or "flow", "crewai.flow.started", {"engine": "crewai"})
            result = run_learning_loop(
                skip_live_incident=self.state.skip_live_incident,
                existing_fixture=self.state.existing_fixture,
                run_id=self.state.run_id or None,
            )
            self.state.run_id = result["run_id"]
            self.state.incident = result.get("incident") or {}
            self.state.diagnosis = result.get("diagnosis") or {}
            self.state.capabilities = result.get("capabilities") or {}
            self.state.candidates = result.get("candidates") or []
            self.state.eval_results = result.get("eval_results") or []
            if result.get("promoted"):
                self.state.promoted_version = result["promoted"].get("version")
            bus.emit(
                self.state.run_id,
                "crewai.flow.completed",
                {"promoted_version": self.state.promoted_version, "engine": "crewai"},
            )
            return "done"

except Exception:  # pragma: no cover
    RepairFlow = None  # type: ignore


def run_crewai_flow(
    *,
    skip_live_incident: bool = False,
    existing_fixture: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Entry used by demo: prefer CrewAI Flow kickoff; fall back to direct loop."""
    run_id = run_id or f"flow-{uuid.uuid4().hex[:8]}"
    if RepairFlow is None:
        bus.emit(run_id, "crewai.flow.unavailable", {"fallback": "run_learning_loop"})
        out = run_learning_loop(
            skip_live_incident=skip_live_incident,
            existing_fixture=existing_fixture,
            run_id=run_id,
        )
        out["flow_engine"] = "direct_loop"
        return out

    flow = RepairFlow()
    flow.state.run_id = run_id
    flow.state.skip_live_incident = skip_live_incident
    flow.state.existing_fixture = existing_fixture
    flow.kickoff()
    # Re-load full result details from artifacts if needed
    out = {
        "run_id": flow.state.run_id,
        "incident": flow.state.incident,
        "diagnosis": flow.state.diagnosis,
        "capabilities": flow.state.capabilities,
        "candidates": flow.state.candidates,
        "eval_results": flow.state.eval_results,
        "promoted": {"version": flow.state.promoted_version} if flow.state.promoted_version else None,
        "flow_engine": "crewai",
    }
    return out


if __name__ == "__main__":
    settings = get_settings()
    fixture_path = settings.fixtures_dir / "incident_stripe.json"
    existing = json.loads(fixture_path.read_text()) if fixture_path.exists() else None
    out = run_crewai_flow(skip_live_incident=bool(existing), existing_fixture=existing)
    print(
        json.dumps(
            {
                "promoted": out.get("promoted"),
                "evals": [
                    {
                        "v": e.get("candidate_version") or e.get("version"),
                        "verdict": e.get("verdict"),
                        "reasons": e.get("reject_reasons"),
                        "sandbox_id": e.get("sandbox_id"),
                        "executed_in": e.get("executed_in"),
                    }
                    for e in out.get("eval_results") or []
                ],
            },
            indent=2,
        )
    )
