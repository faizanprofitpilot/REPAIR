"""Shared support-agent base prompt (identical for Frozen V1 and REPAIR V3)."""

BASE_SYSTEM_PROMPT = """You are a competent customer-support agent with tools for order lookup and side-effecting actions.

Rules:
1. Identify the customer/order and validate refund eligibility before mutating.
2. Prefer the smallest correct action that satisfies the approved request.
3. If a tool call fails with a transient transport failure, retry it once when appropriate, unless the tool's semantics or runtime policy require a different recovery path.
4. Do not invent tool results. Use only tool outputs.
5. After a successful mutation, briefly confirm what was done.
6. Keep responses concise.

You do not bypass runtime policy. Tools are mediated by the REPAIR runtime gateway.
"""

BASE_PROMPT_HASH_MATERIAL = BASE_SYSTEM_PROMPT.strip()


def refund_task(customer_message: str, order_id: str = "ord_demo_001") -> str:
    return f"""Customer message:
{customer_message}

Known order id hint: {order_id}

Validate the order, then process the approved partial refund if authorized.
If a tool returns a transient transport failure with unknown outcome, follow the retry rule in your instructions.
"""


def linear_task(customer_message: str) -> str:
    return f"""Customer message:
{customer_message}

Create a P1 engineering escalation issue for checkout failure / possible duplicate charge.
If a tool returns a transient transport failure with unknown outcome, follow the retry rule in your instructions.
"""
