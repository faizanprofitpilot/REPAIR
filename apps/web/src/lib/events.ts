export type RepairEvent = {
  ts: string;
  run_id: string;
  seq: number;
  type: string;
  payload: Record<string, unknown>;
};

export const ENGINE_URL =
  process.env.NEXT_PUBLIC_ENGINE_URL || "http://127.0.0.1:8000";

/** Every event type the demo surface reacts to (all already emitted by the engine). */
export const EVENT_TYPES = [
  "run.started",
  "run.completed",
  "run.failed",
  "tool.proposed",
  "tool.started",
  "tool.completed",
  "runtime.allowed",
  "runtime.matched",
  "runtime.blocked",
  "fault.injected",
  "incident.detected",
  "incident.prevented",
  "external_state.updated",
  "crewai.flow.started",
  "crewai.flow.completed",
  "diagnosis.mode",
  "diagnosis.completed",
  "research.started",
  "research.evidence",
  "research.fallback",
  "capability.resolved",
  "policy.synthesis_mode",
  "policy.generated",
  "policy.rejected_by_guard",
  "evaluation.started",
  "evaluation.completed",
  "evaluation.failed",
  "candidate.rejected",
  "candidate.promoted",
  "registry.updated",
  "verification.started",
  "verification.succeeded",
  "verification.failed",
  "action.prevented",
] as const;

export const STAGES = [
  "EXECUTE",
  "FAIL",
  "DIAGNOSE",
  "RESEARCH",
  "SYNTHESIZE",
  "TEST",
  "PROMOTE",
  "ENFORCE",
  "TRANSFER",
] as const;
export type Stage = (typeof STAGES)[number];

export type DecisionState =
  | "IDLE"
  | "PROPOSED"
  | "ALLOW"
  | "AMBIGUOUS"
  | "BLOCKED"
  | "VERIFYING"
  | "VERIFIED"
  | "PREVENTED";

export type SponsorKey = "one" | "youcom" | "crewai" | "daytona";
export type SponsorStatus = "idle" | "active" | "done";

export type Citation = { url?: string; title?: string; quote?: string };

export type ResearchView = {
  tool_id: string;
  source: string;
  search_uuid?: string;
  query?: string;
  citations: Citation[];
  nativeSafeReplay?: string;
  mechanism?: string | null;
  stateVerification?: string;
  verificationMechanism?: string | null;
};

export type PolicyView = {
  version?: number;
  id?: string;
  rationale?: string;
  match?: Record<string, unknown>;
  require?: string[];
  prohibit?: string[];
  raw: unknown;
};

export type GateView = {
  version?: number;
  verdict: "REJECTED" | "PROMOTED";
  sandbox_id?: string;
  executed_in?: string;
  reasons?: string[];
  metrics?: Record<string, unknown>;
};

export type DemoModel = {
  stage: Stage;
  stagesDone: Set<Stage>;
  act: 0 | 1 | 2 | 3;
  domain: "stripe" | "linear" | null;
  /** true while a V1 (no rule) sub-run is active */
  controlRun: boolean;
  ruleInstalled: boolean;
  decision: DecisionState;
  proposedTool?: string;
  proposedBy?: string;
  proposedParams?: Record<string, unknown>;
  decisionKey: number;
  matchedRule?: string;
  requiredSteps?: string[];
  reasons?: string[];
  verifiedRef?: string;
  verifiedUrl?: string;
  faultActive: boolean;

  stripe: {
    authorizedCents: number;
    refundedCents: number;
    refundCount: number;
    duplicate: boolean;
    refundIds: string[];
  };
  linear: {
    frozenCount: number | null;
    repairedCount: number | null;
    liveCount: number;
    prevented: boolean;
    latestIdentifier?: string;
  };

  diagnosis?: { observed?: string; root?: string; model?: string; mode?: string };
  synthesisMode?: string;
  research: ResearchView[];
  policies: PolicyView[];
  gates: GateView[];
  promotedVersion?: number;

  sponsors: Record<SponsorKey, { status: SponsorStatus; note?: string }>;

  promptHash?: string;
  runDone: boolean;
  runFailed?: string;
  finalHero: boolean;
  climaxReached: boolean;
};

export function emptyModel(): DemoModel {
  return {
    stage: "EXECUTE",
    stagesDone: new Set(),
    act: 0,
    domain: null,
    controlRun: false,
    ruleInstalled: false,
    decision: "IDLE",
    decisionKey: 0,
    faultActive: false,
    stripe: {
      authorizedCents: 1290,
      refundedCents: 0,
      refundCount: 0,
      duplicate: false,
      refundIds: [],
    },
    linear: { frozenCount: null, repairedCount: null, liveCount: 0, prevented: false },
    research: [],
    policies: [],
    gates: [],
    sponsors: {
      one: { status: "idle" },
      youcom: { status: "idle" },
      crewai: { status: "idle" },
      daytona: { status: "idle" },
    },
    runDone: false,
    finalHero: false,
    climaxReached: false,
  };
}

const VERIFY_TOOLS = new Set(["linear.find_by_marker", "stripe.list_refunds"]);

function str(v: unknown): string | undefined {
  return v === undefined || v === null ? undefined : String(v);
}

function setStage(m: DemoModel, s: Stage) {
  if (m.stage !== s) {
    m.stagesDone.add(m.stage);
    m.stage = s;
  }
}

/** Pure reducer: full event list → presentation model. Display-only; no runtime semantics. */
export function deriveModel(events: RepairEvent[]): DemoModel {
  const m = emptyModel();

  for (const e of events) {
    const p = e.payload || {};
    switch (e.type) {
      case "run.started": {
        const scenario = str(p.scenario);
        if (p.prompt_hash) m.promptHash = str(p.prompt_hash);
        if (scenario === "stripe_incident") {
          m.act = 1;
          m.domain = "stripe";
          m.controlRun = Boolean(p.frozen);
          m.decision = "IDLE";
          m.decisionKey++;
          setStage(m, "EXECUTE");
        } else if (scenario === "learning_loop") {
          m.act = 2;
          setStage(m, "DIAGNOSE");
        } else if (scenario === "linear_holdout") {
          m.act = 3;
          m.domain = "linear";
          m.controlRun = Boolean(p.frozen);
          m.ruleInstalled = !p.frozen;
          m.linear.liveCount = 0;
          m.decision = "IDLE";
          m.decisionKey++;
          m.matchedRule = undefined;
          m.requiredSteps = undefined;
          m.reasons = undefined;
          m.verifiedRef = undefined;
          setStage(m, "ENFORCE");
        }
        break;
      }

      case "tool.proposed": {
        const tool = str(p.tool_id) || "";
        const by = str(p.proposed_by);
        const isVerify = VERIFY_TOOLS.has(tool) || by === "runtime";
        // Display-only guard: never let the runtime's own verification lookup
        // reset the canvas once an unsafe replay has been blocked.
        if (isVerify || m.decision === "BLOCKED" || m.decision === "VERIFYING") {
          break;
        }
        m.decision = "PROPOSED";
        m.decisionKey++;
        m.proposedTool = tool;
        m.proposedBy = by;
        m.proposedParams = (p.params as Record<string, unknown>) || undefined;
        break;
      }

      case "runtime.matched": {
        m.matchedRule = `${p.policy_id ?? "rule"} v${p.version ?? ""}`;
        m.reasons = (p.reasons as string[]) || undefined;
        m.requiredSteps = (p.required_steps as string[]) || undefined;
        if (p.verdict === "BLOCK") {
          m.decision = "BLOCKED";
          m.decisionKey++;
        }
        break;
      }

      case "runtime.allowed": {
        const tool = str(p.tool_id) || "";
        if (VERIFY_TOOLS.has(tool) || m.decision === "BLOCKED" || m.decision === "VERIFYING") break;
        m.decision = "ALLOW";
        m.decisionKey++;
        break;
      }

      case "tool.started": {
        const tool = str(p.tool_id) || "";
        m.sponsors.one = { status: "active", note: tool };
        if (tool === "stripe.create_refund") {
          // CommitThenDisconnect: the external mutation commits even when the
          // agent never sees the response. Count committed mutations.
          m.stripe.refundCount += 1;
          m.stripe.refundedCents += Number(
            ((p.params as Record<string, unknown>) || {}).amount ?? 1290,
          );
          if (m.stripe.refundCount >= 2) {
            m.stripe.duplicate = true;
            setStage(m, "FAIL");
          }
        }
        if (tool === "linear.create_issue") {
          m.linear.liveCount += 1;
        }
        break;
      }

      case "tool.completed": {
        m.sponsors.one = { status: "done", note: str(p.tool_id) };
        const tool = str(p.tool_id) || "";
        const body = (p.body as Record<string, unknown>) || {};
        if (tool === "stripe.create_refund" && body.id) {
          const id = String(body.id);
          if (!m.stripe.refundIds.includes(id)) m.stripe.refundIds = [...m.stripe.refundIds, id];
        }
        if (tool === "linear.create_issue") {
          const issue =
            ((body.data as Record<string, unknown> | undefined)?.issueCreate as Record<string, unknown> | undefined)
              ?.issue as Record<string, string> | undefined;
          if (issue?.identifier) m.linear.latestIdentifier = issue.identifier;
        }
        break;
      }

      case "fault.injected": {
        m.faultActive = true;
        m.decision = "AMBIGUOUS";
        m.decisionKey++;
        if (m.domain === "stripe") setStage(m, "FAIL");
        break;
      }

      case "incident.detected": {
        m.stripe.authorizedCents = Number(p.authorized_cents ?? 1290);
        m.stripe.refundedCents = Number(p.refunded_cents ?? m.stripe.refundedCents);
        m.stripe.refundCount = Number(p.refund_count ?? m.stripe.refundCount);
        m.stripe.duplicate = m.stripe.refundCount >= 2;
        if (Array.isArray(p.refund_ids)) {
          m.stripe.refundIds = (p.refund_ids as unknown[]).map(String);
        }
        setStage(m, "FAIL");
        break;
      }

      case "external_state.updated": {
        const s = p.stripe as Record<string, unknown> | undefined;
        if (s) {
          m.stripe.authorizedCents = Number(s.authorized_cents ?? m.stripe.authorizedCents);
          m.stripe.refundedCents = Number(s.refunded_cents ?? m.stripe.refundedCents);
          m.stripe.refundCount = Number(s.refund_count ?? m.stripe.refundCount);
          m.stripe.duplicate = m.stripe.refundCount >= 2;
          if (Array.isArray(s.refund_ids)) {
            m.stripe.refundIds = (s.refund_ids as unknown[]).map(String);
          }
        }
        const l = p.linear as Record<string, unknown> | undefined;
        if (l) {
          const count = Number(l.issue_count ?? 0);
          const issues = (l.issues as Array<Record<string, string>>) || [];
          if (l.frozen) m.linear.frozenCount = count;
          else {
            m.linear.repairedCount = count;
            if (count === 1 && m.climaxReached) m.linear.prevented = true;
          }
          if (issues[0]?.identifier) m.linear.latestIdentifier = issues[0].identifier;
        }
        break;
      }

      case "crewai.flow.started": {
        m.act = 2;
        m.sponsors.crewai = { status: "active", note: "flow started" };
        setStage(m, "DIAGNOSE");
        break;
      }
      case "diagnosis.mode": {
        m.sponsors.crewai = { status: "active", note: str(p.model) || "diagnosing" };
        m.diagnosis = {
          ...(m.diagnosis || {}),
          model: str(p.model),
          mode: str(p.mode),
        };
        setStage(m, "DIAGNOSE");
        break;
      }
      case "diagnosis.completed": {
        m.diagnosis = {
          ...(m.diagnosis || {}),
          observed: str(p.observed_failure),
          root: str(p.root_cause),
        };
        setStage(m, "DIAGNOSE");
        break;
      }

      case "research.started": {
        m.sponsors.youcom = { status: "active", note: str(p.target) };
        if (m.act === 2) setStage(m, "RESEARCH");
        break;
      }
      case "research.evidence":
      case "research.fallback": {
        const caps = (p.capabilities as Record<string, unknown>) || {};
        const evidence = (caps.evidence as Record<string, unknown>) || {};
        const citations =
          (p.citations as Citation[]) || (evidence.citations as Citation[]) || [];
        const view: ResearchView = {
          tool_id: str(p.tool_id) || "",
          source: str(p.source) || str(caps.source) || "unknown",
          search_uuid: str(p.search_uuid) || str(evidence.search_uuid),
          query: str(p.query) || str(evidence.query),
          citations,
          nativeSafeReplay: str(caps.native_safe_replay),
          mechanism: (caps.mechanism as string | null) ?? null,
          stateVerification: str(caps.state_verification),
          verificationMechanism: (caps.verification_mechanism as string | null) ?? null,
        };
        // de-dupe reused evidence for same tool
        const idx = m.research.findIndex((r) => r.tool_id === view.tool_id);
        if (idx >= 0) {
          if (view.citations.length) m.research[idx] = view;
        } else {
          m.research.push(view);
        }
        m.sponsors.youcom = {
          status: "done",
          note: view.source === "live" ? "live" : view.source,
        };
        if (m.act === 2) setStage(m, "RESEARCH");
        break;
      }

      case "policy.synthesis_mode": {
        m.sponsors.crewai = { status: "active", note: `synthesizing v${p.attempt ?? ""}` };
        m.synthesisMode = str(p.mode);
        if (p.model) m.diagnosis = { ...(m.diagnosis || {}), model: str(p.model) };
        setStage(m, "SYNTHESIZE");
        break;
      }
      case "policy.generated": {
        const pol = (p.policy as Record<string, unknown>) || {};
        m.policies.push({
          version: Number(pol.version ?? 0) || undefined,
          id: str(pol.id),
          rationale: str(pol.rationale),
          match: (pol.match as Record<string, unknown>) || undefined,
          require: (pol.require as string[]) || [],
          prohibit: (pol.prohibit as string[]) || [],
          raw: pol,
        });
        setStage(m, "SYNTHESIZE");
        break;
      }

      case "evaluation.started": {
        m.sponsors.daytona = { status: "active", note: `testing v${p.version ?? ""}` };
        setStage(m, "TEST");
        break;
      }
      case "evaluation.completed": {
        m.sponsors.daytona = { status: "active", note: str(p.verdict) };
        break;
      }
      case "candidate.rejected": {
        const metrics = (p.metrics as Record<string, unknown>) || {};
        m.gates.push({
          version: Number(p.version ?? 0) || undefined,
          verdict: "REJECTED",
          sandbox_id: str(metrics.sandbox_id),
          executed_in: str(metrics.executed_in),
          reasons: (p.reject_reasons as string[]) || [],
          metrics,
        });
        m.sponsors.daytona = { status: "active", note: `v${p.version} rejected` };
        setStage(m, "TEST");
        break;
      }
      case "candidate.promoted": {
        const metrics = (p.metrics as Record<string, unknown>) || {};
        m.gates.push({
          version: Number(p.version ?? 0) || undefined,
          verdict: "PROMOTED",
          sandbox_id: str(metrics.sandbox_id),
          executed_in: str(metrics.executed_in),
          metrics,
        });
        m.promotedVersion = Number(p.version ?? 0) || undefined;
        m.sponsors.daytona = { status: "done", note: `v${p.version} promoted` };
        setStage(m, "PROMOTE");
        break;
      }
      case "registry.updated": {
        m.ruleInstalled = true;
        setStage(m, "PROMOTE");
        break;
      }
      case "crewai.flow.completed": {
        m.sponsors.crewai = { status: "done", note: "adapted" };
        break;
      }

      case "runtime.blocked": {
        m.decision = "BLOCKED";
        m.decisionKey++;
        m.proposedTool = str(p.tool_id) || m.proposedTool;
        m.reasons = (p.reasons as string[]) || m.reasons;
        m.requiredSteps = (p.required_steps as string[]) || m.requiredSteps;
        if (p.matched_policy_id) m.matchedRule = `${p.matched_policy_id} v${m.promotedVersion ?? ""}`;
        m.climaxReached = true;
        setStage(m, "ENFORCE");
        break;
      }
      case "verification.started": {
        m.decision = "VERIFYING";
        m.decisionKey++;
        break;
      }
      case "verification.succeeded": {
        m.decision = "VERIFIED";
        m.decisionKey++;
        const detail = (p.detail as Record<string, unknown>) || {};
        const issues = (detail.issues as Array<Record<string, string>>) || [];
        const refunds = (detail.refunds as Array<Record<string, string>>) || [];
        if (issues[0]) {
          m.verifiedRef = issues[0].identifier || issues[0].id;
          m.verifiedUrl = issues[0].url;
        } else if (refunds[0]) {
          m.verifiedRef = refunds[0].id;
        }
        break;
      }
      case "verification.failed": {
        m.decision = "BLOCKED";
        m.decisionKey++;
        break;
      }
      case "action.prevented": {
        m.decision = "PREVENTED";
        m.decisionKey++;
        m.linear.prevented = true;
        setStage(m, "TRANSFER");
        break;
      }

      case "run.completed": {
        const scenario = str(p.scenario);
        if (scenario === "linear_holdout" && p.frozen === false) {
          m.finalHero = m.climaxReached;
          setStage(m, "TRANSFER");
        }
        if (scenario === "full_demo") {
          m.runDone = true;
          if (m.climaxReached) m.finalHero = true;
        }
        break;
      }
      case "run.failed": {
        m.runDone = true;
        m.runFailed = str(p.error) || "run failed";
        break;
      }
      default:
        break;
    }
  }

  return m;
}

/* ---------- Human-language helpers (derived from real fields only) ---------- */

export function humanTool(tool?: string): string {
  if (!tool) return "—";
  const map: Record<string, string> = {
    "stripe.get_order": "read order",
    "stripe.create_refund": "create refund",
    "stripe.list_refunds": "list refunds",
    "linear.create_issue": "create issue",
    "linear.find_by_marker": "look up existing operation",
  };
  return map[tool] || tool;
}

export function humanRequire(step: string): string {
  const map: Record<string, string> = {
    establish_safe_replay: "establish a safe replay",
    verify_authoritative_state: "verify authoritative state",
    preserve_operation_identity: "preserve the original operation identity",
    correlated_replay: "replay only with the original identity",
  };
  return map[step] || step.replace(/_/g, " ");
}

export function humanMechanism(m?: string | null): string | undefined {
  if (!m) return undefined;
  const map: Record<string, string> = {
    idempotency_key: "idempotency key",
    list_refunds: "listing committed operations",
    issues_filter_description_contains: "operation-marker lookup",
  };
  return map[m] || m.replace(/_/g, " ");
}

export function policyToEnglish(p?: PolicyView): string {
  if (!p) return "";
  const match = p.match || {};
  const outcome = match.outcome_state ? String(match.outcome_state) : null;
  const persistent = match.persistent_side_effect === true;
  const effect = match.effect_type ? String(match.effect_type) : "action";

  const subject = persistent
    ? `a ${effect} with a persistent side effect`
    : `a ${effect}`;
  const when = outcome ? `has an ${outcome} outcome` : "occurs";

  const prohibits = (p.prohibit || []).includes("uncorrelated_replay")
    ? "never blindly replay it."
    : "";

  const reqs = (p.require || []).map(humanRequire);
  const requireText = reqs.length
    ? `First ${reqs.join(", then ")}.`
    : "";

  return `If ${subject} ${when}, ${prohibits} ${requireText}`.replace(/\s+/g, " ").trim();
}

export function policyBreadth(p?: PolicyView): "broad" | "narrow" | undefined {
  if (!p) return undefined;
  return p.match?.outcome_state ? "narrow" : "broad";
}

export function humanReject(reasons: string[] = []): string {
  const parts: string[] = [];
  if (reasons.includes("unnecessary_verification_operations")) parts.push("over-broad — adds verification to safe operations");
  if (reasons.includes("safety_cases_failed")) parts.push("misses a safety case");
  if (reasons.includes("negative_controls_failed")) parts.push("blocks a benign action");
  if (reasons.includes("verdict_incorrect")) parts.push("wrong verdict on eval cases");
  if (reasons.includes("vocabulary_guard")) parts.push("domain-specific vocabulary");
  return parts.join("; ") || reasons.join(", ");
}

export function capabilityConclusion(r?: ResearchView): string {
  if (!r) return "";
  if (r.nativeSafeReplay === "available") {
    return `Safe replay is available natively${
      r.mechanism ? ` via ${humanMechanism(r.mechanism)}` : ""
    }. A retry can preserve the original operation identity.`;
  }
  if (r.stateVerification === "available") {
    return `No native safe replay. Authoritative verification is available${
      r.verificationMechanism ? ` via ${humanMechanism(r.verificationMechanism)}` : ""
    } — the runtime must check before any replay.`;
  }
  return "Capability unresolved.";
}

export function money(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

/* ---------- Live Execution proof rows (display-only) ---------- */

export type ProofActor =
  | "AGENT"
  | "RUNTIME"
  | "ONE"
  | "FAULT"
  | "WORLD"
  | "CREWAI"
  | "YOU.COM"
  | "DAYTONA"
  | "VERIFIED";

export type ProofTone = "neutral" | "amber" | "block" | "success" | "live";

export type ProofRow = {
  key: string;
  ts: string;
  seq: number;
  actor: ProofActor;
  text: string;
  evidence?: string;
  tone?: ProofTone;
  live?: boolean;
};

const CREATE_TOOLS = new Set(["stripe.create_refund", "linear.create_issue"]);

export function shortId(id?: string | null, kind: "auto" | "uuid" | "refund" | "run" = "auto"): string {
  if (!id) return "—";
  const s = String(id);
  if (kind === "refund" || s.startsWith("re_") || s.startsWith("pi_")) {
    if (s.length <= 14) return s;
    return `${s.slice(0, 7)}…${s.slice(-3)}`;
  }
  if (kind === "run" || s.startsWith("demo-") || s.startsWith("op_")) {
    if (s.length <= 12) return s;
    return `${s.slice(0, 10)}…`;
  }
  // uuid-ish
  if (s.includes("-") && s.length > 12) return `${s.slice(0, 8)}…`;
  if (s.length > 14) return `${s.slice(0, 8)}…${s.slice(-3)}`;
  return s;
}

export function clock(ts?: string): string {
  if (!ts) return "--:--:--";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts.slice(11, 19) || ts;
  return d.toLocaleTimeString("en-GB", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function domainFromUrl(url?: string): string | undefined {
  if (!url) return undefined;
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return undefined;
  }
}

function linearIssueFromBody(body: Record<string, unknown> | undefined): string | undefined {
  if (!body) return undefined;
  const issue =
    ((body.data as Record<string, unknown> | undefined)?.issueCreate as Record<string, unknown> | undefined)?.issue as
      | Record<string, string>
      | undefined;
  return issue?.identifier;
}

/**
 * Pure display reducer: SSE events → compact human proof rows.
 * Caps to last 6. Never invents provider calls.
 */
export function deriveProofRows(events: RepairEvent[]): ProofRow[] {
  const rows: ProofRow[] = [];
  let pendingBlocked: { op_id: string; tool_id: string; seq: number } | null = null;
  let noDispatchEmitted = false;

  const push = (
    e: RepairEvent,
    actor: ProofActor,
    text: string,
    extra?: { evidence?: string; tone?: ProofTone; live?: boolean; keySuffix?: string },
  ) => {
    rows.push({
      key: `${e.run_id}-${e.seq}-${extra?.keySuffix || actor}`,
      ts: clock(e.ts),
      seq: e.seq,
      actor,
      text,
      evidence: extra?.evidence,
      tone: extra?.tone,
      live: extra?.live,
    });
  };

  for (const e of events) {
    const p = e.payload || {};
    const tool = str(p.tool_id) || "";

    switch (e.type) {
      case "tool.proposed": {
        const by = str(p.proposed_by);
        if (by === "runtime" || VERIFY_TOOLS.has(tool)) break;
        if (CREATE_TOOLS.has(tool) || tool === "stripe.get_order") {
          const label =
            tool === "stripe.create_refund"
              ? "proposes fresh refund replay"
              : tool === "linear.create_issue"
                ? "proposes Linear issue replay"
                : `proposes ${humanTool(tool)}`;
          // Prefer "proposes" wording for mutations; first refund is also a proposal
          const text =
            tool === "stripe.create_refund" && !rows.some((r) => r.text.includes("refund"))
              ? "proposes Stripe refund"
              : tool === "linear.create_issue" && !pendingBlocked
                ? "proposes Linear issue create"
                : label;
          push(e, "AGENT", text, { evidence: shortId(str(p.op_id), "run") });
        }
        break;
      }

      case "tool.started": {
        const opId = str(p.op_id) || "";

        if (pendingBlocked && !noDispatchEmitted) {
          if (opId === pendingBlocked.op_id) {
            // Blocked create actually dispatched — never claim NO CREATE DISPATCH
            pendingBlocked = null;
          } else if (VERIFY_TOOLS.has(tool)) {
            // First outbound after block is verification/read and create never started
            push(e, "ONE", "NO CREATE DISPATCH", {
              evidence: "NO OUTBOUND MUTATION",
              tone: "block",
              keySuffix: "nodispatch",
            });
            noDispatchEmitted = true;
            pendingBlocked = null;
          } else {
            // Some other tool started first — do not invent the forensic row
            pendingBlocked = null;
          }
        }

        if (tool === "stripe.create_refund") {
          push(e, "ONE", "Stripe refund dispatched", { evidence: shortId(opId, "run") });
        } else if (tool === "linear.create_issue") {
          push(e, "ONE", "Linear issue create dispatched", { evidence: shortId(opId, "run") });
        } else if (tool === "linear.find_by_marker") {
          push(e, "ONE", "Linear verification read", {
            evidence: shortId(str((p.params as Record<string, unknown> | undefined)?.marker), "run"),
          });
        } else if (tool === "stripe.list_refunds") {
          push(e, "ONE", "Stripe verification read");
        } else if (tool === "stripe.get_order") {
          push(e, "ONE", "Stripe order read");
        }
        break;
      }

      case "tool.completed": {
        const body = (p.body as Record<string, unknown>) || {};
        if (tool === "stripe.create_refund" && body.id) {
          push(e, "WORLD", `refund ${shortId(String(body.id), "refund")} created`);
        }
        if (tool === "linear.create_issue") {
          const ident = linearIssueFromBody(body);
          if (ident) push(e, "WORLD", `issue ${ident} created`);
        }
        break;
      }

      case "fault.injected": {
        push(e, "FAULT", "success committed; response hidden from agent", { tone: "amber" });
        break;
      }

      case "incident.detected": {
        const count = Number(p.refund_count ?? 0);
        const cents = Number(p.refunded_cents ?? 0);
        push(e, "WORLD", `${count} refunds · ${money(cents)}`, {
          evidence: count >= 2 ? "DUPLICATE MUTATION" : undefined,
          tone: count >= 2 ? "block" : "neutral",
        });
        break;
      }

      case "diagnosis.mode": {
        const mode = str(p.mode);
        const model = str(p.model) || "model";
        push(e, "CREWAI", `${mode === "openai" ? "LIVE" : mode?.toUpperCase() || "MODE"} · ${model} diagnosing`, {
          live: mode === "openai",
          tone: mode === "openai" ? "live" : "neutral",
        });
        break;
      }

      case "diagnosis.completed": {
        push(e, "CREWAI", "failure pattern identified");
        break;
      }

      case "research.evidence":
      case "research.fallback": {
        const caps = (p.capabilities as Record<string, unknown>) || {};
        const evidence = (caps.evidence as Record<string, unknown>) || {};
        const source = str(p.source) || str(caps.source) || (e.type === "research.fallback" ? "fallback" : "unknown");
        const uuid = str(p.search_uuid) || str(evidence.search_uuid);
        const cites = (p.citations as Citation[]) || (evidence.citations as Citation[]) || [];
        const domain = domainFromUrl(cites[0]?.url);
        const live = source === "live";
        push(e, "YOU.COM", `${live ? "LIVE" : source.toUpperCase()} · ${shortId(uuid, "uuid")}`, {
          evidence: domain,
          live,
          tone: live ? "live" : "amber",
        });
        break;
      }

      case "policy.synthesis_mode": {
        const mode = str(p.mode);
        push(e, "CREWAI", `${mode === "openai" ? "LIVE" : mode?.toUpperCase() || "MODE"} · synthesizing runtime rule`, {
          live: mode === "openai",
          tone: mode === "openai" ? "live" : "neutral",
        });
        break;
      }

      case "candidate.rejected": {
        const metrics = (p.metrics as Record<string, unknown>) || {};
        const executed = str(metrics.executed_in);
        const sandbox = str(metrics.sandbox_id);
        push(e, "DAYTONA", `${shortId(sandbox, "uuid")} · V${p.version ?? "?"} REJECTED`, {
          evidence: executed === "daytona" ? "executed_in=daytona" : executed,
          live: executed === "daytona",
          tone: "amber",
        });
        break;
      }

      case "candidate.promoted": {
        const metrics = (p.metrics as Record<string, unknown>) || {};
        const executed = str(metrics.executed_in);
        const sandbox = str(metrics.sandbox_id);
        push(e, "DAYTONA", `${shortId(sandbox, "uuid")} · V${p.version ?? "?"} PROMOTED`, {
          evidence: executed === "daytona" ? "executed_in=daytona" : executed,
          live: executed === "daytona",
          tone: "success",
        });
        break;
      }

      case "runtime.blocked": {
        const opId = str(p.op_id) || "";
        if (CREATE_TOOLS.has(tool) && opId) {
          pendingBlocked = { op_id: opId, tool_id: tool, seq: e.seq };
          noDispatchEmitted = false;
        }
        push(e, "RUNTIME", `BLOCKED ${humanTool(tool)}`, {
          evidence: shortId(opId, "run"),
          tone: "block",
        });
        break;
      }

      case "verification.started": {
        // Do NOT emit NO CREATE DISPATCH here — wait for tool.started verify/read
        push(e, "RUNTIME", "authoritative verification required", {
          evidence: shortId(str(p.op_id), "run"),
        });
        break;
      }

      case "verification.succeeded": {
        const detail = (p.detail as Record<string, unknown>) || {};
        const issues = (detail.issues as Array<Record<string, string>>) || [];
        const refunds = (detail.refunds as Array<Record<string, string>>) || [];
        const ref = issues[0]?.identifier || refunds[0]?.id;
        push(e, "VERIFIED", ref ? `existing operation found · ${ref}` : "existing operation found", {
          tone: "success",
        });
        break;
      }

      case "action.prevented": {
        push(e, "RUNTIME", "DUPLICATE PREVENTED", { tone: "success" });
        break;
      }

      default:
        break;
    }
  }

  return rows.slice(-6);
}

