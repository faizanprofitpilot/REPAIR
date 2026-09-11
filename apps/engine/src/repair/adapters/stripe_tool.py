"""Stripe actions via One CLI action execute (TEST mode enforced)."""

from __future__ import annotations

from typing import Any

from repair.adapters.one import OneAdapter
from repair.models import ToolResponse


class StripeTool:
    def __init__(self, one: OneAdapter) -> None:
        self.one = one

    def get_balance(self) -> ToolResponse:
        action_id = self.one.resolve_action("stripe", "Retrieve Account Balance", "balance")
        return self.one.execute_action("stripe", action_id)

    def assert_test_mode(self) -> None:
        resp = self.get_balance()
        if not resp.ok:
            raise RuntimeError(f"Stripe balance check failed: {resp.error} {resp.body}")
        body = resp.body or {}
        if body.get("livemode") is True:
            raise RuntimeError(
                "REFUSING TO RUN: Stripe connection is LIVE mode (livemode=true). "
                "Reconnect in One with a TEST secret key (sk_test_…): "
                "`one add stripe` using your Stripe test-mode key, then update "
                "ONE_STRIPE_CONNECTION_KEY in .env. No live refunds will be attempted."
            )

    def seed_payment_intent(
        self,
        amount: int = 3890,
        currency: str = "usd",
        metadata: dict[str, str] | None = None,
    ) -> ToolResponse:
        action_id = self.one.resolve_action(
            "stripe", "Create a PaymentIntent", "create_payment_intent"
        )
        # Stripe form-encoding: nested keys as bracket notation, not JSON objects
        data: dict[str, Any] = {
            "amount": amount,
            "currency": currency,
            "payment_method": "pm_card_visa",
            "confirm": True,
            "automatic_payment_methods[enabled]": True,
            "automatic_payment_methods[allow_redirects]": "never",
        }
        if metadata:
            for k, v in metadata.items():
                data[f"metadata[{k}]"] = v
        return self.one.execute_action(
            "stripe",
            action_id,
            data=data,
            form_url_encoded=True,
        )

    def create_refund(
        self,
        *,
        payment_intent: str | None = None,
        charge: str | None = None,
        amount: int = 1290,
        idempotency_key: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> ToolResponse:
        # Guard every mutation path
        self.assert_test_mode()
        action_id = self.one.resolve_action(
            "stripe", "Create a Refund", "create_refund"
        )
        data: dict[str, Any] = {"amount": amount}
        if payment_intent:
            data["payment_intent"] = payment_intent
        if charge:
            data["charge"] = charge
        if metadata:
            for k, v in metadata.items():
                data[f"metadata[{k}]"] = v
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return self.one.execute_action(
            "stripe",
            action_id,
            data=data,
            headers=headers,
            form_url_encoded=True,
        )

    def list_refunds(self, payment_intent: str, limit: int = 20) -> ToolResponse:
        action_id = self.one.resolve_action("stripe", "List all refunds", "list_refunds")
        return self.one.execute_action(
            "stripe",
            action_id,
            query_params={"payment_intent": payment_intent, "limit": limit},
        )
