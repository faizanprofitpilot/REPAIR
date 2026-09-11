"use client";

import { humanRequire, humanTool, type DemoModel } from "@/lib/events";

const TASK_STRIPE = "Customer approved for a $12.90 partial refund.";
const TASK_LINEAR =
  "Checkout failed multiple times and may have charged the customer twice. Create a P1 engineering escalation.";

type Tone = "neutral" | "allow" | "amber" | "block" | "verify" | "success";

function headline(m: DemoModel): { tone: Tone; title: string; sub: string } {
  switch (m.decision) {
    case "PROPOSED":
      return { tone: "neutral", title: "AGENT TRIES AGAIN", sub: `tool proposed · ${humanTool(m.proposedTool)}` };
    case "ALLOW":
      return {
        tone: "allow",
        title: m.ruleInstalled ? "ALLOWED · rule satisfied" : "ALLOWED · no rule installed",
        sub: humanTool(m.proposedTool),
      };
    case "AMBIGUOUS":
      return {
        tone: "amber",
        title: "IT WORKED — BUT THE AGENT NEVER SAW SUCCESS",
        sub: "CommitThenDisconnect",
      };
    case "BLOCKED":
      return {
        tone: "block",
        title: "STOPPED BEFORE IT RAN",
        sub: `runtime.blocked · ${humanTool(m.proposedTool)} never reached One`,
      };
    case "VERIFYING":
      return {
        tone: "verify",
        title: "CHECKING IF IT ALREADY HAPPENED",
        sub: "authoritative verification",
      };
    case "VERIFIED":
      return {
        tone: "verify",
        title: "ALREADY DONE",
        sub: m.verifiedRef
          ? `Found ${m.verifiedRef}. No second action needed.`
          : "Existing operation found.",
      };
    case "PREVENTED":
      return {
        tone: "success",
        title: "DUPLICATE PREVENTED",
        sub: "Agent received the verified result and continued.",
      };
    default:
      return {
        tone: "neutral",
        title: m.act === 0 ? "READY" : "WAITING FOR AGENT",
        sub: m.act === 0 ? "Press Play full story." : "",
      };
  }
}

export function DecisionCanvas({ m }: { m: DemoModel }) {
  const h = headline(m);
  const task = m.domain === "linear" ? TASK_LINEAR : TASK_STRIPE;
  const showBlockChain = ["BLOCKED", "VERIFYING", "VERIFIED", "PREVENTED"].includes(m.decision);

  const chain: Array<{ key: string; label: string; sub?: string; reached: boolean }> = [
    {
      key: "proposed",
      label: `Agent tries again · ${humanTool(m.proposedTool)}`,
      reached: true,
    },
    { key: "blocked", label: "Stopped before it ran", sub: "runtime.blocked", reached: true },
    {
      key: "verify",
      label: "Checking if it already happened",
      sub: "authoritative verification",
      reached: ["VERIFYING", "VERIFIED", "PREVENTED"].includes(m.decision),
    },
    {
      key: "verified",
      label: m.verifiedRef ? `Already done · ${m.verifiedRef}` : "Already done",
      reached: ["VERIFIED", "PREVENTED"].includes(m.decision),
    },
    {
      key: "prevented",
      label: "Duplicate prevented · never sent to One",
      reached: m.decision === "PREVENTED",
    },
  ];

  return (
    <section className={`canvas tone-${h.tone}`} key={`canvas-${m.decisionKey}`}>
      <header className="canvas__head">
        <div>
          <p className="eyebrow">Safety gate</p>
          <h2 className="canvas__title">
            Runtime decision
          </h2>
        </div>
        <div className="canvas__domain">
          {m.domain === "linear" && (
            <span className="pill pill--unseen">Unseen domain · Linear</span>
          )}
          {m.domain === "stripe" && <span className="pill">Stripe · test mode</span>}
          <span className={`pill ${m.ruleInstalled ? "pill--rule" : ""}`}>
            {m.ruleInstalled
              ? `After learning · V${m.promotedVersion ?? 3}`
              : "Before learning · no rule"}
          </span>
        </div>
      </header>

      <div className="canvas__task">
        <span className="canvas__task-label">Task</span>
        <p>{task}</p>
        {m.domain === "linear" && (
          <p className="canvas__invariant">
            Same agent. Same prompt. Same tools. Same fault.
            {m.ruleInstalled
              ? " Same learned safety rule."
              : " Same situation, no safety rule yet."}
          </p>
        )}
      </div>

      <div className={`canvas__state ${h.tone === "block" ? "canvas__state--flash" : ""}`}>
        <h1 className="canvas__headline">{h.title}</h1>
        {h.sub && <p className="canvas__sub">{h.sub}</p>}
      </div>

      {showBlockChain ? (
        <ol className="chain">
          {chain.map((c) => (
            <li key={c.key} className={`chain__step ${c.reached ? "is-reached" : ""}`}>
              <span className="chain__marker" />
              <span>
                {c.label}
                {c.sub ? <span className="chain__sub"> · {c.sub}</span> : null}
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <dl className="facts">
          <div>
            <dt>Agent proposed</dt>
            <dd>{humanTool(m.proposedTool)}</dd>
          </div>
          <div>
            <dt>Installed rule</dt>
            <dd className="mono">
              {m.ruleInstalled ? m.matchedRule || `v${m.promotedVersion ?? 3}` : "none"}
            </dd>
          </div>
          <div>
            <dt>Fault</dt>
            <dd>{m.faultActive ? "CommitThenDisconnect" : "Ready"}</dd>
          </div>
          <div>
            <dt>Required before retry</dt>
            <dd>
              {m.requiredSteps?.length
                ? m.requiredSteps.map(humanRequire).join(", ")
                : "—"}
            </dd>
          </div>
        </dl>
      )}
    </section>
  );
}
