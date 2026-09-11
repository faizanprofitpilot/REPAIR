"""Operation ledger and tool metadata registry."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from repair.models import (
    ConsequenceLevel,
    EffectType,
    IdentityCarrier,
    LearnedPolicy,
    OperationRecord,
    OutcomeState,
    ToolCapabilities,
    ToolMetadata,
    utcnow,
)


def intent_key(tool_id: str, params: dict[str, Any]) -> str:
    """Stable hash of tool + business params (excludes identity material)."""
    canonical = {k: params[k] for k in sorted(params) if k not in {"idempotency_key", "repair_op_id"}}
    blob = json.dumps({"tool_id": tool_id, "params": canonical}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


DEFAULT_TOOLS: dict[str, ToolMetadata] = {
    "stripe.create_refund": ToolMetadata(
        tool_id="stripe.create_refund",
        effect_type=EffectType.MUTATION,
        persistent_side_effect=True,
        consequence_level=ConsequenceLevel.HIGH,
        identity_carrier=IdentityCarrier.HEADER_IDEMPOTENCY_KEY,
        verification_tool_id="stripe.list_refunds",
        platform="stripe",
        description="Create a Stripe refund",
    ),
    "stripe.list_refunds": ToolMetadata(
        tool_id="stripe.list_refunds",
        effect_type=EffectType.READ,
        persistent_side_effect=False,
        consequence_level=ConsequenceLevel.LOW,
        identity_carrier=IdentityCarrier.NONE,
        platform="stripe",
        description="List Stripe refunds",
    ),
    "stripe.get_order": ToolMetadata(
        tool_id="stripe.get_order",
        effect_type=EffectType.READ,
        persistent_side_effect=False,
        consequence_level=ConsequenceLevel.LOW,
        identity_carrier=IdentityCarrier.NONE,
        platform="stripe",
        description="Read synthetic order state",
    ),
    "linear.create_issue": ToolMetadata(
        tool_id="linear.create_issue",
        effect_type=EffectType.MUTATION,
        persistent_side_effect=True,
        consequence_level=ConsequenceLevel.HIGH,
        identity_carrier=IdentityCarrier.BODY_MARKER_DESCRIPTION,
        verification_tool_id="linear.find_by_marker",
        platform="linear",
        description="Create a Linear issue",
    ),
    "linear.find_by_marker": ToolMetadata(
        tool_id="linear.find_by_marker",
        effect_type=EffectType.READ,
        persistent_side_effect=False,
        consequence_level=ConsequenceLevel.LOW,
        identity_carrier=IdentityCarrier.NONE,
        platform="linear",
        description="Find Linear issue by REPAIR_OP_ID marker",
    ),
}


class OperationLedger:
    def __init__(self) -> None:
        self._by_op: dict[str, OperationRecord] = {}
        self._by_intent: dict[str, list[str]] = {}

    def record(self, record: OperationRecord) -> OperationRecord:
        self._by_op[record.op_id] = record
        self._by_intent.setdefault(record.intent_key, []).append(record.op_id)
        return record

    def get(self, op_id: str) -> OperationRecord | None:
        return self._by_op.get(op_id)

    def latest_for_intent(self, intent_key_value: str) -> OperationRecord | None:
        ids = self._by_intent.get(intent_key_value) or []
        if not ids:
            return None
        return self._by_op[ids[-1]]

    def update_outcome(
        self,
        op_id: str,
        outcome_state: OutcomeState,
        *,
        agent_visible_result: dict[str, Any] | None = None,
        true_external_result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> OperationRecord:
        rec = self._by_op[op_id]
        rec.outcome_state = outcome_state
        rec.updated_at = utcnow()
        if agent_visible_result is not None:
            rec.agent_visible_result = agent_visible_result
        if true_external_result is not None:
            rec.true_external_result = true_external_result
        if error is not None:
            rec.error = error
        return rec

    def all_records(self) -> list[OperationRecord]:
        return list(self._by_op.values())


class PolicyRegistry:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._active: list[LearnedPolicy] = []
        self._capabilities: dict[str, ToolCapabilities] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self._active = []
            self._save()
            return
        data = json.loads(self.path.read_text())
        self._active = [LearnedPolicy.model_validate(p) for p in data.get("active", [])]
        caps = data.get("capabilities", {})
        self._capabilities = {k: ToolCapabilities.model_validate(v) for k, v in caps.items()}

    def _save(self) -> None:
        payload = {
            "active": [p.model_dump(mode="json") for p in self._active],
            "capabilities": {k: v.model_dump(mode="json") for k, v in self._capabilities.items()},
        }
        self.path.write_text(json.dumps(payload, indent=2))

    @property
    def active(self) -> list[LearnedPolicy]:
        return list(self._active)

    def clear(self) -> None:
        self._active = []
        self._save()

    def promote(self, policy: LearnedPolicy) -> None:
        # replace same id
        self._active = [p for p in self._active if p.id != policy.id]
        self._active.append(policy)
        self._save()

    def active_dicts(self) -> list[dict[str, Any]]:
        return [p.model_dump(mode="json") for p in self._active]

    def version_label(self) -> str:
        if not self._active:
            return "V1"
        return f"V{max(p.version for p in self._active)}"

    def set_capabilities(self, tool_id: str, caps: ToolCapabilities) -> None:
        self._capabilities[tool_id] = caps
        self._save()

    def with_empty_active(self) -> "PolicyRegistry":
        """In-memory clone with no active policies (does not touch disk)."""
        clone = PolicyRegistry.__new__(PolicyRegistry)
        clone.path = self.path
        clone._active = []
        clone._capabilities = dict(self._capabilities)
        return clone

    def get_capabilities(self, tool_id: str) -> ToolCapabilities:
        if tool_id in self._capabilities:
            return self._capabilities[tool_id]
        return ToolCapabilities(tool_id=tool_id)

    def tool_meta(self, tool_id: str) -> ToolMetadata:
        if tool_id not in DEFAULT_TOOLS:
            raise KeyError(f"Unknown tool: {tool_id}")
        return DEFAULT_TOOLS[tool_id]
