"use client";

import type { InterceptState } from "@/lib/events";

const COLORS: Record<InterceptState, string> = {
  IDLE: "#6b7280",
  ALLOW: "#22c55e",
  AMBIGUOUS: "#f59e0b",
  BLOCKED: "#ef4444",
  VERIFYING: "#38bdf8",
  PREVENTED: "#a3e635",
};

export function InterceptPanel({
  state,
  lastTool,
  matchedPolicy,
  context,
  reasons,
  requiredSteps,
  verification,
  prevented,
}: {
  state: InterceptState;
  lastTool?: string;
  matchedPolicy?: string;
  context?: Record<string, unknown>;
  reasons?: string[];
  requiredSteps?: string[];
  verification?: Record<string, unknown>;
  prevented?: Record<string, unknown>;
}) {
  const steps: InterceptState[] = [
    "IDLE",
    "ALLOW",
    "AMBIGUOUS",
    "BLOCKED",
    "VERIFYING",
    "PREVENTED",
  ];

  return (
    <section className="intercept">
      <header className="intercept__head">
        <div>
          <p className="eyebrow">Runtime Gateway</p>
          <h2>Intercept</h2>
        </div>
        <div
          className="intercept__badge"
          style={{ borderColor: COLORS[state], color: COLORS[state] }}
        >
          {state}
        </div>
      </header>

      <div className="intercept__rail">
        {steps.map((s) => (
          <div
            key={s}
            className={`rail-step ${state === s ? "rail-step--active" : ""}`}
            style={
              state === s
                ? { boxShadow: `0 0 0 1px ${COLORS[s]}`, color: COLORS[s] }
                : undefined
            }
          >
            {s}
          </div>
        ))}
      </div>

      <dl className="intercept__grid">
        <div>
          <dt>Agent request</dt>
          <dd>{lastTool || "—"}</dd>
        </div>
        <div>
          <dt>Matched policy</dt>
          <dd className="mono">{matchedPolicy || "none"}</dd>
        </div>
        <div>
          <dt>Replay type</dt>
          <dd>{String(context?.replay_type ?? "—")}</dd>
        </div>
        <div>
          <dt>Prior outcome</dt>
          <dd>{String(context?.prior_outcome_state ?? "—")}</dd>
        </div>
        <div>
          <dt>Native safe replay</dt>
          <dd>{String(context?.native_safe_replay ?? "—")}</dd>
        </div>
        <div>
          <dt>Persistent side effect</dt>
          <dd>{String(context?.persistent_side_effect ?? "—")}</dd>
        </div>
        <div>
          <dt>Required steps</dt>
          <dd>{requiredSteps?.join(", ") || "—"}</dd>
        </div>
        <div>
          <dt>Reasons</dt>
          <dd>{reasons?.join(", ") || "—"}</dd>
        </div>
      </dl>

      {(verification || prevented) && (
        <div className="intercept__footer">
          {verification && (
            <p>
              Verification:{" "}
              <span className="mono">
                {verification.found ? "FOUND" : "NOT FOUND"}{" "}
                {String(verification.op_id || "")}
              </span>
            </p>
          )}
          {prevented && (
            <p>
              Action prevented:{" "}
              <span className="mono">{String(prevented.reason || prevented.tool_id)}</span>
            </p>
          )}
        </div>
      )}
    </section>
  );
}
