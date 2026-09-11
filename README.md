# REPAIR

**MEMORY → POLICY. ADVICE → ENFORCEMENT.**

REPAIR turns a real operational failure into a domain-independent runtime policy. The model proposes recovery; a Python gateway is the authority that allows, requires, or blocks tool calls before they reach One.

## Architecture

```
Next.js UI  --SSE-->  FastAPI  -->  CrewAI Flow / Support Agent
                                      |
                                      v
                               Runtime Gateway (interceptor)
                                      |
                    +--------+--------+--------+
                    |        |        |        |
                 Policy   Fault    Ledger   Recovery
                 Engine  Injector
                    |
                    v
              One CLI actions  -->  Stripe TEST / Linear
              You.com Search   -->  capability evidence
              Daytona/local    -->  qualify candidates
```

V1 (frozen) and V3 (repaired) share the same base model instruction, tools, fault (`CommitThenDisconnect`), and starting state. The only meaningful behavioral difference is the promoted runtime policy.

## Sponsor map

| Sponsor | Role in REPAIR |
|---------|----------------|
| **One** | Sole path for Stripe + Linear mutations (`one actions execute`). No local Stripe secret used for actions. |
| **You.com** | Live Search (+Contents when available) for first-party docs; capability resolution with provenance. |
| **CrewAI** | Flow: diagnose → research → synthesize → validate → promote/reject. |
| **Daytona** | Deterministic policy qualification harness (local fallback labeled when API key missing). |

## Clean-data statement

All customer and order data in this demo is synthetic. Stripe runs in **TEST mode only**; Linear runs in a workspace we own and are authorized to modify. No real customer PII is processed. Web research is restricted to first-party technical documentation (`docs.stripe.com`, `linear.app`) and every piece of evidence retains its source URL and retrieval timestamp. Execution traces preserve timestamps and provenance. No unrelated third-party personal data is ingested.

## Safety

Final golden run evidence lives in `runs/golden/` (live One, You.com, Daytona, CrewAI/OpenAI).

Before any Stripe mutation, REPAIR verifies `livemode == false` through One (see `fixtures/preflight/stripe_test_mode.json`). If livemode is true or unproven, mutations stop.

## Quick start

```bash
# Engine (Python 3.12)
cd apps/engine
uv sync
cp ../../.env.example ../../.env   # fill ONE_SECRET + connection keys via `one --agent list`
uv run python -m repair.api.main   # http://127.0.0.1:8000

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

# Reset run artifacts (keeps promoted V3)
uv run python scripts/reset_demo.py --keep-golden
```

### API

- `POST /demo/run` — start demo (`?phases=linear_frozen,linear_repaired`)
- `GET /events?run_id=…` — SSE event stream
- `GET /state` — fault badge, registry version, external snapshots
- `GET /health`

## Policies

- Candidates: `policies/candidates/`
- Promoted: `policies/promoted/v3.json`
- Active registry: `policies/registry.json`

Policy DSL is domain-free (`match` / `require` / `prohibit` / `recovery` / `allow` / `bypass_when`). Vocabulary guard rejects Stripe/Linear/refund-specific tokens.

## Repo layout

- `apps/engine` — FastAPI + runtime + flow + scenarios
- `apps/web` — Next.js intercept UI (SSE consumer)
- `fixtures/` — incident, eval cases, preflight, evidence cache
- `docs/` — submission + demo notes
