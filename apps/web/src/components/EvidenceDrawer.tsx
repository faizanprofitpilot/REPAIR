"use client";

import { clock, type DemoModel, type RepairEvent } from "@/lib/events";
import { ENGINE_URL } from "@/lib/events";

export function EvidenceDrawer({
  m,
  events,
  runId,
  publicState,
}: {
  m: DemoModel;
  events: RepairEvent[];
  runId: string | null;
  publicState: Record<string, unknown>;
}) {
  const latestPolicy = m.policies[m.policies.length - 1];
  return (
    <details className="drawer">
      <summary>Technical evidence</summary>
      <div className="drawer__grid">
        <div>
          <p className="eyebrow">Execution receipts</p>
          <div className="drawer__receipts">
            <p className="mono small">run_id {runId || "—"}</p>
            <p className="mono small">engine {ENGINE_URL}</p>
            <p className="mono small">prompt_hash {m.promptHash || "—"}</p>
            <p className="mono small">
              crewai/openai {m.diagnosis?.mode || m.synthesisMode || "—"}
              {m.diagnosis?.model ? ` · ${m.diagnosis.model}` : ""}
            </p>
            {m.stripe.refundIds.length > 0 && (
              <p className="mono small">stripe refunds {m.stripe.refundIds.join(", ")}</p>
            )}
            {(m.linear.latestIdentifier || m.verifiedRef) && (
              <p className="mono small">linear issue {m.linear.latestIdentifier || m.verifiedRef}</p>
            )}
          </div>
          <p className="eyebrow" style={{ marginTop: "0.6rem" }}>Daytona sandboxes</p>
          {m.gates.length === 0 && <p className="mono small">—</p>}
          {m.gates.map((g, i) => (
            <p className="mono small" key={i}>
              v{g.version} {g.verdict} · {g.executed_in} · {g.sandbox_id}
            </p>
          ))}
          <p className="eyebrow" style={{ marginTop: "0.6rem" }}>You.com search UUIDs</p>
          {m.research.length === 0 && <p className="mono small">—</p>}
          {m.research.map((r) => (
            <p className="mono small" key={r.tool_id}>
              {r.tool_id} · {r.source} · {r.search_uuid || "—"}
            </p>
          ))}
        </div>
        <div>
          <p className="eyebrow">Promoted rule (raw)</p>
          <pre className="json">{latestPolicy ? JSON.stringify(latestPolicy.raw, null, 2) : "—"}</pre>
        </div>
        <div>
          <p className="eyebrow">External raw state</p>
          <pre className="json">
            {JSON.stringify(
              {
                stripe: publicState.stripe,
                linear_frozen: publicState.linear_frozen,
                linear_repaired: publicState.linear_repaired,
              },
              null,
              2,
            )}
          </pre>
        </div>
        <div>
          <p className="eyebrow">Event timeline ({events.length})</p>
          <ul className="timeline">
            {[...events].reverse().map((e) => (
              <li key={`${e.run_id}-${e.seq}`}>
                <span className="mono seq">{e.seq}</span>
                <span className="mono" style={{ color: "var(--muted)", minWidth: "4.2rem" }}>
                  {clock(e.ts)}
                </span>
                <span className="etype">{e.type}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </details>
  );
}
