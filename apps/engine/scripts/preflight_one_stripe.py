#!/usr/bin/env python3
"""Preflight: seed Stripe TEST PaymentIntent and create one refund via One."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from repair.adapters.one import OneAdapter
from repair.adapters.stripe_tool import StripeTool
from repair.config import get_settings


def main() -> int:
    settings = get_settings()
    settings.require_one()
    one = OneAdapter(settings)
    stripe = StripeTool(one)

    print("== assert test mode ==")
    stripe.assert_test_mode()
    print("ok: livemode=false")

    print("== seed payment intent $38.90 ==")
    pi = stripe.seed_payment_intent(amount=3890, metadata={"repair": "preflight"})
    if not pi.ok:
        print("FAIL seed:", pi.status_code, pi.body)
        return 1
    pi_id = (pi.body or {}).get("id")
    print("payment_intent:", pi_id, "status:", (pi.body or {}).get("status"))

    print("== create refund $12.90 ==")
    refund = stripe.create_refund(payment_intent=pi_id, amount=1290)
    if not refund.ok:
        print("FAIL refund:", refund.status_code, refund.body)
        return 1
    body = refund.body or {}
    assert body.get("object") == "refund", body
    # Some Stripe objects omit livemode; never allow an explicit live flag.
    assert body.get("livemode") is not True, body
    assert body.get("status") == "succeeded", body
    print("refund:", body.get("id"), "amount:", body.get("amount"), "status:", body.get("status"), "livemode:", body.get("livemode"))

    out = {
        "payment_intent": pi_id,
        "refund_id": body.get("id"),
        "amount": body.get("amount"),
        "livemode": body.get("livemode"),
        "status": body.get("status"),
        "test_mode_gate": "STRIPE_TEST_MODE_VERIFIED",
    }
    dest = ROOT / "fixtures" / "preflight" / "stripe_refund.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2))
    print("wrote", dest)
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
