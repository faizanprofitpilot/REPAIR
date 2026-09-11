"""Domain models for actions, traces, capabilities, policies, decisions, evaluation."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_op_id() -> str:
    return f"op_{uuid4().hex[:8]}"


class EffectType(str, Enum):
    READ = "read"
    MUTATION = "mutation"


class ConsequenceLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class OutcomeState(str, Enum):
    SUCCESS = "success"
    AMBIGUOUS = "ambiguous"
    DEFINITIVE_FAILURE = "definitive_failure"
    PRECOMMIT_FAILURE = "precommit_failure"
    PENDING = "pending"


class ReplayType(str, Enum):
    NONE = "none"
    CORRELATED = "correlated"
    UNCORRELATED = "uncorrelated"


class Availability(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class Verdict(str, Enum):
    ALLOW = "ALLOW"
    REQUIRE = "REQUIRE"
    BLOCK = "BLOCK"


class RequireStep(str, Enum):
    ESTABLISH_SAFE_REPLAY = "establish_safe_replay"
    VERIFY_AUTHORITATIVE_STATE = "verify_authoritative_state"
    PRESERVE_OPERATION_IDENTITY = "preserve_operation_identity"


class ProhibitAction(str, Enum):
    UNCORRELATED_REPLAY = "uncorrelated_replay"
    MUTATION = "mutation"
    CONTINUE = "continue"


class AllowAction(str, Enum):
    CORRELATED_REPLAY = "correlated_replay"
    RETRY = "retry"
    CONTINUE = "continue"


class BypassWhen(str, Enum):
    READ_ONLY_ACTION = "read_only_action"
    DEFINITIVE_PRECOMMIT_FAILURE = "definitive_precommit_failure"
    CONFIRMED_FAILED_MUTATION = "confirmed_failed_mutation"
    NO_PRIOR_OPERATION = "no_prior_operation"


class IdentityCarrier(str, Enum):
    HEADER_IDEMPOTENCY_KEY = "header:Idempotency-Key"
    BODY_MARKER_DESCRIPTION = "body_marker:description"
    NONE = "none"


class Citation(BaseModel):
    url: str
    title: str | None = None
    quote: str | None = None
    page_age: str | None = None


class CapabilityEvidence(BaseModel):
    query: str
    search_uuid: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    extracted_at: datetime = Field(default_factory=utcnow)
    latency_ms: float | None = None
    provider: str = "you.com"
    source: Literal["live", "cached"] = "live"
    verified_at: datetime | None = None
    raw_highlights: list[str] = Field(default_factory=list)


class ToolMetadata(BaseModel):
    tool_id: str
    effect_type: EffectType
    persistent_side_effect: bool
    consequence_level: ConsequenceLevel = ConsequenceLevel.MEDIUM
    identity_carrier: IdentityCarrier = IdentityCarrier.NONE
    verification_tool_id: str | None = None
    platform: str | None = None
    description: str = ""


class ToolCapabilities(BaseModel):
    tool_id: str
    native_safe_replay: Availability = Availability.UNKNOWN
    mechanism: str | None = None
    preserve_operation_identity_required: bool = False
    state_verification: Availability = Availability.UNAVAILABLE
    verification_mechanism: str | None = None
    evidence: CapabilityEvidence | None = None
    preflight_result: dict[str, Any] | None = None
    source: Literal["live", "cached", "preflight", "registry"] = "registry"


class ActionRequest(BaseModel):
    op_id: str = Field(default_factory=new_op_id)
    intent_key: str
    tool_id: str
    params: dict[str, Any] = Field(default_factory=dict)
    proposed_by: Literal["llm", "runtime", "script"] = "llm"
    replay_of: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)


class OperationRecord(BaseModel):
    op_id: str
    intent_key: str
    tool_id: str
    params: dict[str, Any] = Field(default_factory=dict)
    outcome_state: OutcomeState = OutcomeState.PENDING
    agent_visible_result: dict[str, Any] | None = None
    true_external_result: dict[str, Any] | None = None
    identity_material: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    error: str | None = None


class PolicyMatch(BaseModel):
    effect_type: EffectType | None = None
    persistent_side_effect: bool | None = None
    outcome_state: OutcomeState | None = None
    consequence_level: ConsequenceLevel | None = None
    replay_type: ReplayType | None = None


class PolicyRecovery(BaseModel):
    if_native_safe_replay_available: list[RequireStep] = Field(
        default_factory=lambda: [
            RequireStep.PRESERVE_OPERATION_IDENTITY,
        ]
    )
    otherwise: list[RequireStep] = Field(
        default_factory=lambda: [RequireStep.VERIFY_AUTHORITATIVE_STATE]
    )


class LearnedPolicy(BaseModel):
    id: str
    version: int
    rationale: str = ""
    match: PolicyMatch = Field(default_factory=PolicyMatch)
    require: list[RequireStep] = Field(default_factory=list)
    prohibit: list[ProhibitAction] = Field(default_factory=list)
    recovery: PolicyRecovery = Field(default_factory=PolicyRecovery)
    allow: list[AllowAction] = Field(default_factory=list)
    bypass_when: list[BypassWhen] = Field(default_factory=list)


class ExecutionContext(BaseModel):
    request: ActionRequest
    tool: ToolMetadata
    capabilities: ToolCapabilities
    prior: OperationRecord | None = None
    prior_outcome_state: OutcomeState | None = None
    replay_type: ReplayType = ReplayType.NONE
    active_policy_versions: list[str] = Field(default_factory=list)
    required_steps_satisfied: list[RequireStep] = Field(default_factory=list)


class RuntimeDecision(BaseModel):
    verdict: Verdict
    matched_policy_id: str | None = None
    matched_policy_version: int | None = None
    reasons: list[str] = Field(default_factory=list)
    required_steps: list[RequireStep] = Field(default_factory=list)
    context_snapshot: dict[str, Any] = Field(default_factory=dict)


class EvalCase(BaseModel):
    id: str
    title: str
    context: dict[str, Any]
    expected_verdict: Verdict
    expected_required_steps: list[RequireStep] = Field(default_factory=list)
    baseline_tool_operations: int = 1
    category: Literal["safety", "negative_control", "benign", "recovery", "regression"]


class CaseResult(BaseModel):
    case_id: str
    verdict: Verdict
    required_steps: list[RequireStep] = Field(default_factory=list)
    additional_tool_operations: int = 0
    passed: bool
    detail: str = ""


class EvalResult(BaseModel):
    candidate_id: str
    candidate_version: int
    case_results: list[CaseResult] = Field(default_factory=list)
    safety_cases_passed: str = "0/0"
    negative_controls_passed: str = "0/0"
    verdict_correctness: str = "0/0"
    unnecessary_verification_operations: int = 0
    additional_tool_operations: int = 0
    regression_failures: int = 0
    measured_latency_ms: float | None = None
    verdict: Literal["PROMOTE", "REJECT"] = "REJECT"
    reject_reasons: list[str] = Field(default_factory=list)
    sandbox_id: str | None = None
    executed_in: Literal["daytona", "local_fallback"] = "local_fallback"
    engine_sha256: str | None = None


class ToolResponse(BaseModel):
    ok: bool
    status_code: int | None = None
    body: Any = None
    error: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    duration_ms: float | None = None
