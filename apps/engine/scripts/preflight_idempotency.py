#!/usr/bin/env python3
"""Preflight: does One forward Idempotency-Key to Stripe?"""

from __future__ import annotations

import json
import sys
import uuid
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
    stripe.assert_test_mode()

    pi = stripe.seed_payment_intent(amount=3890, metadata={"repair": "idempotency-preflight"})
    if not pi.ok:
        print("FAIL seed:", pi.body)
        return 1
    pi_id = (pi.body or {}).get("id")
    key = f"repair-preflight-{uuid.uuid4().hex[:12]}"

    print("payment_intent:", pi_id)
    print("idempotency_key:", key)

    r1 = stripe.create_refund(payment_intent=pi_id, amount=1290, idempotency_key=key)
    r2 = stripe.create_refund(payment_intent=pi_id, amount=1290, idempotency_key=key)
    print("r1:", r1.ok, (r1.body or {}).get("id"), r1.status_code)
    print("r2:", r2.ok, (r2.body or {}).get("id"), r2.status_code)

    listed = stripe.list_refunds(pi_id)
    data = (listed.body or {}).get("data") or []
    ids = [d.get("id") for d in data]
    print("refunds on PI:", ids)

    same_id = (r1.body or {}).get("id") and (r1.body or {}).get("id") == (r2.body or {}).get("id")
    single = len(data) == 1
    header_passthrough_ok = bool(r1.ok and r2.ok and same_id and single)

    out = {
        "payment_intent": pi_id,
        "idempotency_key": key,
        "refund_1": (r1.body or {}).get("id"),
        "refund_2": (r2.body or {}).get("id"),
        "refund_count": len(data),
        "same_id": same_id,
        "header_passthrough_ok": header_passthrough_ok,
        "native_safe_replay": "available" if header_passthrough_ok else "unavailable",
    }
    dest = ROOT / "fixtures" / "preflight" / "stripe_idempotency.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2))
    print("wrote", dest)
    print("RESULT:", "PASS — header preserved" if header_passthrough_ok else "FAIL — header not preserved / duplicate created")
    # Non-zero only on hard errors; false passthrough is a recorded outcome, not a crash
    return 0 if r1.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
