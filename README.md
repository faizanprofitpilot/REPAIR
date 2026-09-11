# REPAIR

**An AI agent that turns operational mistakes into machine-enforced runtime rules.**

> It didn’t learn the answer. It changed how it operates.

---

## What REPAIR does

REPAIR is a **safety layer for AI agents**. When an agent makes a costly operational mistake, REPAIR does not just remember the incident in a prompt. It turns that experience into a **tested, machine-enforced runtime rule**.

Most systems “learn” by stuffing advice into memory. REPAIR goes further: diagnose → gather live evidence → propose a policy → qualify it deterministically → **install it as authority outside the model**.

**The model is not the authority boundary.** The model can still propose a bad action. A deterministic Python runtime gateway can stop that action **before it reaches One**.

REPAIR does **not** retrain model weights. The learning loop is:

**experience → diagnosis → live evidence → proposed policy → deterministic testing → promotion → runtime enforcement**

---

## The demo in 60 seconds

1. A support agent is authorized to refund **$12.90** through Stripe (TEST mode) via One.
2. The refund **succeeds**. Stripe did not fail.
3. REPAIR deliberately simulates a post-commit transport failure (`CommitThenDisconnect`): the mutation commits, but the agent **never receives** the success response.
4. The unprotected agent retries the same refund.
5. The customer is refunded twice: **$25.80** instead of **$12.90**.
6. REPAIR diagnoses the failure class: an outside-world change whose result looked uncertain to the agent.
7. **CrewAI** coordinates the adaptation loop.
8. **You.com** retrieves live first-party documentation (not model memory).
9. **Daytona** tests proposed rules inside ephemeral sandboxes.
10. The first overbroad rule is **rejected**.
11. A refined general rule is **approved and installed**.
12. We reproduce the same failure pattern in an **unseen** domain: Linear.
13. **Without** the rule: **2** Linear issues.
14. **With** the learned rule: the model still proposes the retry, but REPAIR **blocks it before it reaches One**.
15. REPAIR verifies the original Linear issue already exists.
16. Final result: **1** issue — duplicate prevented.

**Stripe flow**

`$12.90 authorized` → success committed, response lost → blind retry → `$25.80 refunded`

**REPAIR**

diagnose → research → test → install rule

**Linear transfer**

without rule = **2** issues · with rule = **1** issue

---

## The key idea

| Soft learning | REPAIR |
|---|---|
| Memory / prompt advice | **Policy** installed in a registry |
| “Please don’t do that again” | **Enforcement** before tool dispatch |

Same agent. Same prompt. Same tools. Same simulated fault.  
The difference after learning is the **runtime rule**, not a smarter prompt.

### The learned rule (plain English)

> If an action changes the outside world and its result is uncertain, never blindly repeat it. First determine whether it already happened, or safely replay the exact same operation.

This is **not** “when using Stripe refunds, do X.”  
It describes a **failure class** (ambiguous side effects). That is why transfer to Linear matters.

---

## How the sponsor stack is used

**One**  
Executes the real authenticated Stripe and Linear actions. The blocked Linear retry is **never dispatched** to One.

**CrewAI**  
Coordinates the learning loop: diagnose → research → synthesize → validate → promote/reject.

**You.com Search API**  
Retrieves current first-party technical documentation so policy synthesis is grounded in **live evidence**, not model memory.

**Daytona**  
Runs deterministic qualification of proposed policies inside **ephemeral sandboxes**. The first overbroad candidate is rejected; the refined candidate passes. Live qualification requires a real Daytona result and sandbox ID (sandboxes are deleted after the run; audit logs retain the IDs).

---

## Architecture

```
Next.js UI  --SSE-->  FastAPI  -->  CrewAI Flow / Support Agent
                                      |
                                      v
                         Runtime Gateway (allow / require / block)
                                      |
                 +----------+---------+----------+
                 |          |         |          |
              Policy     Fault     Ledger    Recovery
              Engine    Injector
                 |
                 v
           One  -->  Stripe TEST / Linear
           You.com  -->  live capability evidence
           Daytona  -->  qualify candidates (sandbox_id required)
```

**Frontend (recording UI):** four paced acts, each calling one backend phase (`stripe_frozen` → `learn` → `linear_frozen` → `linear_repaired`) while preserving session evidence across separate `run_id`s.

**CLI:** can still run a full demo under a **single** `run_id` via `repair.scenarios.demo`.

V1 (no rule) and V3 (learned rule) share the same agent prompt, tools, and fault. The behavioral difference is the promoted runtime policy.

---

## Why the Linear transfer matters

It proves the learned policy describes the **failure class**, not Stripe-specific behavior. Same agent, same prompt, same fault — different domain.

---

## Safety & clean data

All customer and order data is **synthetic**. Stripe runs in **TEST mode only**. Linear runs in a workspace we own and are authorized to modify. No real customer PII is processed.

Web research is restricted to first-party docs (`docs.stripe.com`, `linear.app`). Evidence keeps source URL and retrieval provenance. Execution traces keep timestamps.

Before any Stripe mutation, REPAIR verifies `livemode == false` through One (`fixtures/preflight/stripe_test_mode.json`). If livemode is **true** or **unproven**, mutations stop.

Frozen live qualification evidence: `runs/golden/`.

---

## Technical details

- **Runtime gateway** — intercepts tool proposals; allow / require / block before One.
- **V1 vs V3** — empty registry (control) vs promoted `ambiguous_side_effect_recovery` v3.
- **Policy DSL** — domain-free `match` / `require` / `prohibit` / `recovery` / `allow` / `bypass_when`.
- **Vocabulary guard** — rejects Stripe/Linear/refund-specific tokens in candidates.
- **Registry** — `policies/candidates/`, `policies/promoted/`, `policies/registry.json`.
- **API** — `POST /demo/run`, `GET /events?run_id=…` (SSE), `GET /state`, `GET /health`.

---

## Quick start

```bash
# Engine (Python 3.12)
cd apps/engine
uv sync
cp ../../.env.example ../../.env   # fill ONE_SECRET + connection keys via `one --agent list`
# Prefer unset proxies for Daytona SDK reliability:
env -u HTTP_PROXY -u HTTPS_PROXY uv run python -m repair.api.main   # http://127.0.0.1:8000

# Web
cd apps/web
pnpm install
NEXT_PUBLIC_ENGINE_URL=http://127.0.0.1:8000 pnpm dev
```

### Demo CLI

```bash
cd apps/engine
# Frozen Stripe incident (2 TEST refunds under fault)
uv run python -m repair.scenarios.stripe_incident --frozen

# Learning loop (reject V2, promote V3)
uv run python -m repair.flow.repair_flow

# Linear holdout
uv run python -m repair.scenarios.linear_holdout --frozen
uv run python -m repair.scenarios.linear_holdout --repaired

# Full demo under one run_id
uv run python -m repair.scenarios.demo

# Or paced phases (same as the UI acts)
uv run python -m repair.scenarios.demo --phases stripe_frozen
uv run python -m repair.scenarios.demo --phases learn
uv run python -m repair.scenarios.demo --phases linear_frozen
uv run python -m repair.scenarios.demo --phases linear_repaired

# Reset run artifacts (keeps promoted V3)
uv run python scripts/reset_demo.py --keep-golden
```

### API

- `POST /demo/run` — start demo (`?phases=stripe_frozen` or comma-separated phases)
- `GET /events?run_id=…` — SSE event stream
- `GET /state` — fault badge, registry version, external snapshots
- `GET /health`

---

## Repo layout

- `apps/engine` — FastAPI, runtime gateway, CrewAI flow, scenarios
- `apps/web` — Next.js UI (SSE; four-act learning loop)
- `fixtures/` — incident, eval cases, preflight, evidence cache
- `policies/` — candidates, promoted, active registry
- `runs/golden/` — frozen live qualification artifacts
- `docs/` — submission + demo notes
