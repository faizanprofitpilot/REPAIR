"""Runtime gateway — the single choke point for side-effecting tool calls."""

from __future__ import annotations

from typing import Any

from repair.adapters.linear_tool import LinearTool
from repair.adapters.one import OneAdapter
from repair.adapters.stripe_tool import StripeTool
from repair.events.bus import EventBus, bus as default_bus
from repair.models import (
    ActionRequest,
    ExecutionContext,
    OperationRecord,
    OutcomeState,
    ReplayType,
    RequireStep,
    RuntimeDecision,
    ToolResponse,
    Verdict,
    new_op_id,
)
from repair.runtime.fault import FaultInjector, ToolTransportError
from repair.runtime.policy_engine import evaluate_policies
from repair.runtime.recovery import RecoveryExecutor
from repair.runtime.registry import OperationLedger, PolicyRegistry, intent_key


class Gateway:
    def __init__(
        self,
        *,
        one: OneAdapter,
        registry: PolicyRegistry,
        ledger: OperationLedger | None = None,
        fault: FaultInjector | None = None,
        event_bus: EventBus | None = None,
        run_id: str = "default",
        synthetic_orders: dict[str, Any] | None = None,
    ) -> None:
        self.one = one
        self.registry = registry
        self.ledger = ledger or OperationLedger()
        self.fault = fault or FaultInjector()
        self.bus = event_bus or default_bus
        self.run_id = run_id
        self.stripe = StripeTool(one)
        self.linear = LinearTool(one)
        self.synthetic_orders = synthetic_orders or {}
        self._linear_team_id: str | None = None
        self.recovery = RecoveryExecutor(
            execute_tool=self._raw_execute,
            ledger_update=self.ledger.update_outcome,
        )

    def set_run_id(self, run_id: str) -> None:
        self.run_id = run_id

    def build_context(self, request: ActionRequest) -> ExecutionContext:
        tool = self.registry.tool_meta(request.tool_id)
        caps = self.registry.get_capabilities(request.tool_id)
        prior = self.ledger.latest_for_intent(request.intent_key)
        # Exclude current pending if same op
        if prior and prior.op_id == request.op_id:
            # look for previous
            records = [r for r in self.ledger.all_records() if r.intent_key == request.intent_key and r.op_id != request.op_id]
            prior = records[-1] if records else None

        replay_type = ReplayType.NONE
        if prior and prior.outcome_state in {
            OutcomeState.AMBIGUOUS,
            OutcomeState.PENDING,
            OutcomeState.SUCCESS,
            OutcomeState.DEFINITIVE_FAILURE,
            OutcomeState.PRECOMMIT_FAILURE,
        }:
            if request.replay_of and request.replay_of == prior.op_id:
                replay_type = ReplayType.CORRELATED
            elif prior.outcome_state == OutcomeState.AMBIGUOUS:
                replay_type = ReplayType.UNCORRELATED
            elif prior.params == request.params and prior.outcome_state != OutcomeState.SUCCESS:
                replay_type = ReplayType.UNCORRELATED

        return ExecutionContext(
            request=request,
            tool=tool,
            capabilities=caps,
            prior=prior,
            prior_outcome_state=prior.outcome_state if prior else None,
            replay_type=replay_type,
            active_policy_versions=[f"{p.id}:v{p.version}" for p in self.registry.active],
        )

    def _context_dict(self, ctx: ExecutionContext) -> dict[str, Any]:
        return {
            "effect_type": ctx.tool.effect_type.value,
            "persistent_side_effect": ctx.tool.persistent_side_effect,
            "prior_outcome_state": ctx.prior_outcome_state.value if ctx.prior_outcome_state else None,
            "outcome_state": ctx.prior_outcome_state.value if ctx.prior_outcome_state else None,
            "consequence_level": ctx.tool.consequence_level.value,
            "replay_type": ctx.replay_type.value,
            "prior": ctx.prior.model_dump(mode="json") if ctx.prior else None,
            "capabilities": ctx.capabilities.model_dump(mode="json"),
            "required_steps_satisfied": [s.value for s in ctx.required_steps_satisfied],
        }

    def execute(
        self,
        tool_id: str,
        params: dict[str, Any],
        *,
        proposed_by: str = "llm",
        headers: dict[str, str] | None = None,
        identity_material: str | None = None,
        replay_of: str | None = None,
        skip_policy: bool = False,
    ) -> dict[str, Any]:
        key = intent_key(tool_id, params)
        request = ActionRequest(
            op_id=new_op_id(),
            intent_key=key,
            tool_id=tool_id,
            params=params,
            proposed_by=proposed_by,  # type: ignore[arg-type]
            replay_of=replay_of,
            headers=headers or {},
        )
        self.bus.emit(
            self.run_id,
            "tool.proposed",
            {"tool_id": tool_id, "params": params, "op_id": request.op_id, "proposed_by": proposed_by},
        )

        ctx = self.build_context(request)
        decision: RuntimeDecision
        if skip_policy:
            decision = RuntimeDecision(verdict=Verdict.ALLOW, reasons=["skip_policy"])
        else:
            raw = evaluate_policies(self.registry.active_dicts(), self._context_dict(ctx))
            decision = RuntimeDecision(
                verdict=Verdict(raw["verdict"]),
                matched_policy_id=raw.get("matched_policy_id"),
                matched_policy_version=raw.get("matched_policy_version"),
                reasons=list(raw.get("reasons") or []),
                required_steps=[RequireStep(s) for s in raw.get("required_steps") or []],
                context_snapshot={
                    "effect_type": ctx.tool.effect_type.value,
                    "persistent_side_effect": ctx.tool.persistent_side_effect,
                    "prior_outcome_state": ctx.prior_outcome_state.value if ctx.prior_outcome_state else None,
                    "replay_type": ctx.replay_type.value,
                    "native_safe_replay": ctx.capabilities.native_safe_replay.value,
                },
            )

        if decision.matched_policy_id:
            self.bus.emit(
                self.run_id,
                "runtime.matched",
                {
                    "policy_id": decision.matched_policy_id,
                    "version": decision.matched_policy_version,
                    "verdict": decision.verdict.value,
                    "reasons": decision.reasons,
                    "required_steps": [s.value for s in decision.required_steps],
                    "context": decision.context_snapshot,
                },
            )

        if decision.verdict == Verdict.BLOCK:
            self.bus.emit(
                self.run_id,
                "runtime.blocked",
                {
                    "tool_id": tool_id,
                    "op_id": request.op_id,
                    "reasons": decision.reasons,
                    "required_steps": [s.value for s in decision.required_steps],
                    "matched_policy_id": decision.matched_policy_id,
                },
            )
            # Runtime executes verification when required
            if RequireStep.VERIFY_AUTHORITATIVE_STATE in decision.required_steps and ctx.prior:
                self.bus.emit(self.run_id, "verification.started", {"op_id": ctx.prior.op_id})
                vtool = ctx.tool.verification_tool_id or "linear.find_by_marker"
                result = self.recovery.verify_authoritative_state(
                    ctx.prior,
                    vtool,
                    marker=ctx.prior.identity_material,
                )
                self.bus.emit(
                    self.run_id,
                    "verification.succeeded" if result["found"] else "verification.failed",
                    result,
                )
                self.bus.emit(
                    self.run_id,
                    "action.prevented",
                    {"tool_id": tool_id, "reason": "expected_postcondition_present" if result["found"] else "verification_inconclusive"},
                )
                if result["found"]:
                    issues = (result.get("detail") or {}).get("issues") or []
                    refunds = (result.get("detail") or {}).get("refunds") or []
                    if issues:
                        issue = issues[0]
                        return {
                            "ok": True,
                            "blocked": True,
                            "verified": True,
                            "message": f"operation already completed: {issue.get('identifier')} {issue.get('url')}",
                            "issue": issue,
                            "decision": decision.model_dump(mode="json"),
                        }
                    if refunds:
                        return {
                            "ok": True,
                            "blocked": True,
                            "verified": True,
                            "message": f"operation already completed: refund {refunds[0].get('id')}",
                            "refund": refunds[0],
                            "decision": decision.model_dump(mode="json"),
                        }
                    return {
                        "ok": True,
                        "blocked": True,
                        "verified": True,
                        "message": "operation already completed (verified)",
                        "detail": result.get("detail"),
                        "decision": decision.model_dump(mode="json"),
                    }
            return {
                "ok": False,
                "blocked": True,
                "error": "Blocked by REPAIR runtime policy",
                "decision": decision.model_dump(mode="json"),
            }

        if decision.verdict == Verdict.REQUIRE:
            self.bus.emit(
                self.run_id,
                "runtime.required",
                {
                    "tool_id": tool_id,
                    "required_steps": [s.value for s in decision.required_steps],
                },
            )
            if RequireStep.PRESERVE_OPERATION_IDENTITY in decision.required_steps and ctx.prior:
                # Correlated replay path
                identity = ctx.prior.identity_material
                return self._dispatch(
                    request,
                    identity_material=identity,
                    extra_headers={"Idempotency-Key": identity} if identity else {},
                    decision=decision,
                )

        self.bus.emit(self.run_id, "runtime.allowed", {"tool_id": tool_id, "op_id": request.op_id})
        return self._dispatch(
            request,
            identity_material=identity_material,
            extra_headers=headers or {},
            decision=decision,
        )

    def _raw_execute(
        self,
        tool_id: str,
        params: dict[str, Any],
        **kwargs: Any,
    ) -> ToolResponse:
        # Used by recovery — returns ToolResponse
        result = self.execute(tool_id, params, **kwargs)
        if isinstance(result, dict) and "body" in result:
            return ToolResponse(
                ok=bool(result.get("ok")),
                status_code=result.get("status_code"),
                body=result.get("body"),
                error=result.get("error"),
            )
        # wrap agent-facing dict
        return ToolResponse(ok=bool(result.get("ok")), body=result, error=result.get("error"))

    def _dispatch(
        self,
        request: ActionRequest,
        *,
        identity_material: str | None,
        extra_headers: dict[str, str],
        decision: RuntimeDecision,
    ) -> dict[str, Any]:
        tool = self.registry.tool_meta(request.tool_id)
        # Establish identity for mutations
        identity = identity_material
        headers = dict(extra_headers)
        params = dict(request.params)

        if tool.identity_carrier.value == "header:Idempotency-Key":
            if not identity:
                identity = f"repair-{request.op_id}"
            headers.setdefault("Idempotency-Key", identity)
        elif tool.identity_carrier.value == "body_marker:description":
            if not identity:
                identity = request.op_id
            desc = params.get("description") or ""
            marker = f"REPAIR_OP_ID={identity}"
            if marker not in desc:
                params["description"] = (desc.rstrip() + f"\n\n{marker}").strip()

        record = OperationRecord(
            op_id=request.op_id,
            intent_key=request.intent_key,
            tool_id=request.tool_id,
            params=params,
            identity_material=identity,
            outcome_state=OutcomeState.PENDING,
        )
        self.ledger.record(record)

        self.bus.emit(
            self.run_id,
            "tool.started",
            {"tool_id": request.tool_id, "op_id": request.op_id, "params": params},
        )

        resp = self._call_tool(request.tool_id, params, headers)

        if self.fault.should_inject(request.tool_id, resp.ok):
            detail = self.fault.inject(request.tool_id)
            self.ledger.update_outcome(
                request.op_id,
                OutcomeState.AMBIGUOUS,
                true_external_result={"ok": True, "status_code": resp.status_code, "body": resp.body},
                agent_visible_result=None,
                error="transport interrupted",
            )
            self.bus.emit(self.run_id, "fault.injected", detail)
            self.bus.emit(
                self.run_id,
                "tool.completed",
                {"tool_id": request.tool_id, "op_id": request.op_id, "outcome": "ambiguous"},
            )
            raise ToolTransportError(
                "connection interrupted before a response was received; outcome unknown",
                transient=True,
            )

        if resp.ok:
            self.ledger.update_outcome(
                request.op_id,
                OutcomeState.SUCCESS,
                agent_visible_result={"ok": True, "body": resp.body},
                true_external_result={"ok": True, "body": resp.body},
            )
            self.bus.emit(
                self.run_id,
                "tool.completed",
                {"tool_id": request.tool_id, "op_id": request.op_id, "outcome": "success", "body": resp.body},
            )
            return {
                "ok": True,
                "op_id": request.op_id,
                "body": resp.body,
                "status_code": resp.status_code,
                "decision": decision.model_dump(mode="json"),
            }

        # Classify failure
        status = resp.status_code or 0
        if status and 400 <= status < 500:
            outcome = OutcomeState.PRECOMMIT_FAILURE
        else:
            outcome = OutcomeState.DEFINITIVE_FAILURE
        self.ledger.update_outcome(
            request.op_id,
            outcome,
            agent_visible_result={"ok": False, "error": resp.error, "body": resp.body},
            true_external_result={"ok": False, "error": resp.error, "body": resp.body},
            error=resp.error,
        )
        self.bus.emit(
            self.run_id,
            "tool.completed",
            {"tool_id": request.tool_id, "op_id": request.op_id, "outcome": outcome.value, "error": resp.error},
        )
        return {
            "ok": False,
            "op_id": request.op_id,
            "error": resp.error,
            "body": resp.body,
            "status_code": resp.status_code,
            "decision": decision.model_dump(mode="json"),
        }

    def _call_tool(self, tool_id: str, params: dict[str, Any], headers: dict[str, str]) -> ToolResponse:
        if tool_id == "stripe.create_refund":
            return self.stripe.create_refund(
                payment_intent=params.get("payment_intent"),
                charge=params.get("charge"),
                amount=int(params.get("amount", 1290)),
                idempotency_key=headers.get("Idempotency-Key"),
            )
        if tool_id == "stripe.list_refunds":
            return self.stripe.list_refunds(params["payment_intent"])
        if tool_id == "stripe.get_order":
            order_id = params.get("order_id", "ord_demo_001")
            order = self.synthetic_orders.get(order_id) or {
                "order_id": order_id,
                "customer": "Avery Example",
                "email": "customer@example.com",
                "total_cents": 3890,
                "approved_refund_cents": 1290,
                "already_refunded_cents": 0,
                "refund_authorized": True,
                "return_required": False,
            }
            return ToolResponse(ok=True, status_code=200, body=order)
        if tool_id == "linear.create_issue":
            team_id = params.get("team_id") or self._linear_team_id
            if not team_id:
                team_id = self.linear.resolve_team_id()
                self._linear_team_id = team_id
            return self.linear.create_issue(
                team_id=team_id,
                title=params["title"],
                description=params.get("description", ""),
                priority=int(params.get("priority", 1)),
            )
        if tool_id == "linear.find_by_marker":
            return self.linear.find_issues_by_marker(params["marker"])
        raise ValueError(f"Unknown tool_id: {tool_id}")
