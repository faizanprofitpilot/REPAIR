export type RepairEvent = {
  ts: string;
  run_id: string;
  seq: number;
  type: string;
  payload: Record<string, unknown>;
};

export type InterceptState =
  | "IDLE"
  | "ALLOW"
  | "AMBIGUOUS"
  | "BLOCKED"
  | "VERIFYING"
  | "PREVENTED";

export function deriveIntercept(events: RepairEvent[]): {
  state: InterceptState;
  lastTool?: string;
  matchedPolicy?: string;
  context?: Record<string, unknown>;
  reasons?: string[];
  requiredSteps?: string[];
  verification?: Record<string, unknown>;
  prevented?: Record<string, unknown>;
} {
  let state: InterceptState = "IDLE";
  let lastTool: string | undefined;
  let matchedPolicy: string | undefined;
  let context: Record<string, unknown> | undefined;
  let reasons: string[] | undefined;
  let requiredSteps: string[] | undefined;
  let verification: Record<string, unknown> | undefined;
  let prevented: Record<string, unknown> | undefined;

  for (const e of events) {
    const p = e.payload || {};
    if (e.type === "tool.proposed") {
      lastTool = String(p.tool_id || "");
      state = "IDLE";
    }
    if (e.type === "runtime.allowed") {
      state = "ALLOW";
      lastTool = String(p.tool_id || lastTool || "");
    }
    if (e.type === "fault.injected") {
      state = "AMBIGUOUS";
    }
    if (e.type === "runtime.matched") {
      matchedPolicy = `${p.policy_id}:v${p.version}`;
      context = (p.context as Record<string, unknown>) || undefined;
      reasons = (p.reasons as string[]) || undefined;
      requiredSteps = (p.required_steps as string[]) || undefined;
      if (p.verdict === "BLOCK") state = "BLOCKED";
      if (p.verdict === "ALLOW") state = "ALLOW";
    }
    if (e.type === "runtime.blocked") {
      state = "BLOCKED";
      reasons = (p.reasons as string[]) || reasons;
      requiredSteps = (p.required_steps as string[]) || requiredSteps;
      lastTool = String(p.tool_id || lastTool || "");
    }
    if (e.type === "verification.started") {
      state = "VERIFYING";
    }
    if (e.type === "verification.succeeded" || e.type === "verification.failed") {
      verification = p;
      state = e.type === "verification.succeeded" ? "VERIFYING" : "BLOCKED";
    }
    if (e.type === "action.prevented") {
      state = "PREVENTED";
      prevented = p;
    }
  }

  return { state, lastTool, matchedPolicy, context, reasons, requiredSteps, verification, prevented };
}

export const ENGINE_URL =
  process.env.NEXT_PUBLIC_ENGINE_URL || "http://127.0.0.1:8000";
