"""Recovery executors: correlated replay + authoritative state verification."""

from __future__ import annotations

from typing import Any, Callable

from repair.models import OperationRecord, OutcomeState, RequireStep, ToolResponse


class RecoveryExecutor:
    def __init__(
        self,
        *,
        execute_tool: Callable[..., ToolResponse],
        ledger_update: Callable[..., OperationRecord],
    ) -> None:
        self.execute_tool = execute_tool
        self.ledger_update = ledger_update

    def correlated_replay(
        self,
        prior: OperationRecord,
        *,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Re-issue the same mutation preserving operation identity."""
        identity = prior.identity_material
        params = dict(prior.params)
        headers: dict[str, str] = {}
        if identity and identity.startswith("repair-"):
            headers["Idempotency-Key"] = identity
        resp = self.execute_tool(
            prior.tool_id,
            params,
            headers=headers,
            identity_material=identity,
            proposed_by="runtime",
            replay_of=prior.op_id,
            skip_policy=True,
        )
        return {
            "step": "correlated_replay",
            "ok": resp.ok if hasattr(resp, "ok") else bool(resp.get("ok")),
            "result": resp.body if hasattr(resp, "body") else resp,
        }

    def verify_authoritative_state(
        self,
        prior: OperationRecord,
        verification_tool_id: str,
        *,
        marker: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if verification_tool_id == "stripe.list_refunds":
            params["payment_intent"] = prior.params.get("payment_intent")
        elif verification_tool_id == "linear.find_by_marker":
            params["marker"] = marker or prior.identity_material
        resp = self.execute_tool(
            verification_tool_id,
            params,
            proposed_by="runtime",
            skip_policy=True,
        )
        found = False
        detail: dict[str, Any] = {}
        body = resp.body if hasattr(resp, "body") else resp
        if verification_tool_id == "stripe.list_refunds":
            data = (body or {}).get("data") or []
            found = len(data) >= 1
            detail = {"refund_count": len(data), "refunds": data}
        elif verification_tool_id == "linear.find_by_marker":
            nodes = (((body or {}).get("data") or {}).get("issues") or {}).get("nodes") or []
            found = len(nodes) >= 1
            detail = {"issue_count": len(nodes), "issues": nodes}

        if found:
            self.ledger_update(
                prior.op_id,
                OutcomeState.SUCCESS,
                agent_visible_result={"verified": True, **detail},
            )
        return {
            "step": "verify_authoritative_state",
            "found": found,
            "detail": detail,
            "ok": True,
        }
