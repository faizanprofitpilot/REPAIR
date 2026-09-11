"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { InterceptPanel } from "@/components/InterceptPanel";
import {
  ENGINE_URL,
  deriveIntercept,
  type RepairEvent,
} from "@/lib/events";

type PublicState = {
  fault_active?: boolean;
  fault_detail?: Record<string, unknown>;
  registry_version?: string;
  phase?: string;
  stripe?: Record<string, unknown>;
  linear_frozen?: Record<string, unknown>;
  linear_repaired?: Record<string, unknown>;
  last_run_id?: string | null;
};

const CUSTOMER =
  "Checkout failed multiple times and I may have been charged twice. Please refund the duplicate.";

export default function Home() {
  const [events, setEvents] = useState<RepairEvent[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [publicState, setPublicState] = useState<PublicState>({});
  const esRef = useRef<EventSource | null>(null);

  const intercept = useMemo(() => deriveIntercept(events), [events]);

  const refreshState = useCallback(async () => {
    try {
      const res = await fetch(`${ENGINE_URL}/state`);
      if (res.ok) setPublicState(await res.json());
    } catch {
      /* engine may be down */
    }
  }, []);

  useEffect(() => {
    refreshState();
    const t = setInterval(refreshState, 2000);
    return () => clearInterval(t);
  }, [refreshState]);

  const attachSSE = useCallback((id: string) => {
    esRef.current?.close();
    setEvents([]);
    const es = new EventSource(`${ENGINE_URL}/events?run_id=${encodeURIComponent(id)}`);
    esRef.current = es;
    es.onmessage = (msg) => {
      try {
        const parsed = JSON.parse(msg.data) as RepairEvent;
        setEvents((prev) => [...prev, parsed]);
      } catch {
        /* ignore */
      }
    };
    // Named events from sse-starlette
    const types = [
      "run.started",
      "tool.proposed",
      "runtime.allowed",
      "runtime.blocked",
      "runtime.matched",
      "fault.injected",
      "verification.started",
      "verification.succeeded",
      "action.prevented",
      "incident.detected",
      "research.evidence",
      "research.fallback",
      "capability.resolved",
      "policy.generated",
      "candidate.rejected",
      "candidate.promoted",
      "registry.updated",
      "external_state.updated",
      "diagnosis.completed",
      "evaluation.started",
      "run.completed",
      "run.failed",
    ];
    for (const t of types) {
      es.addEventListener(t, (msg) => {
        try {
          const parsed = JSON.parse((msg as MessageEvent).data) as RepairEvent;
          setEvents((prev) => {
            if (prev.some((e) => e.seq === parsed.seq && e.run_id === parsed.run_id)) {
              return prev;
            }
            return [...prev, parsed];
          });
        } catch {
          /* ignore */
        }
      });
    }
    es.onerror = () => {
      /* keep open; EventSource retries */
    };
  }, []);

  const startDemo = async (phases?: string) => {
    setBusy(true);
    setError(null);
    try {
      const qs = phases ? `?phases=${encodeURIComponent(phases)}` : "";
      const res = await fetch(`${ENGINE_URL}/demo/run${qs}`, { method: "POST" });
      const body = await res.json();
      if (!res.ok) {
        setError(body.error || `HTTP ${res.status}`);
        return;
      }
      setRunId(body.run_id);
      attachSSE(body.run_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const research = events.filter(
    (e) => e.type === "research.evidence" || e.type === "research.fallback",
  );
  const policies = events.filter((e) => e.type === "policy.generated");
  const evals = events.filter(
    (e) => e.type === "candidate.rejected" || e.type === "candidate.promoted",
  );
  const external = events.filter((e) => e.type === "external_state.updated");
  const timeline = [...events].slice(-40).reverse();

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand__mark">REPAIR</span>
          <span className="brand__sub">MEMORY → POLICY · ADVICE → ENFORCEMENT</span>
        </div>
        <div className="topbar__meta">
          {publicState.fault_active ? (
            <button
              className="fault-badge"
              title={JSON.stringify(publicState.fault_detail || {})}
              type="button"
            >
              CONTROLLED FAULT ACTIVE · CommitThenDisconnect
            </button>
          ) : (
            <span className="fault-badge fault-badge--idle">FAULT ARMED ON DEMAND</span>
          )}
          <span className="chip">Registry {publicState.registry_version || "—"}</span>
          <span className="chip">Phase {publicState.phase || "idle"}</span>
        </div>
        <div className="topbar__actions">
          <button
            type="button"
            disabled={busy}
            onClick={() => startDemo()}
            className="btn btn--primary"
          >
            Run full demo
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => startDemo("linear_frozen,linear_repaired")}
            className="btn"
          >
            Transfer only
          </button>
        </div>
      </header>

      {error && <div className="banner-error">{error}</div>}
      {runId && (
        <div className="runline">
          run_id <code>{runId}</code> · events {events.length} · engine{" "}
          <code>{ENGINE_URL}</code>
        </div>
      )}

      <div className="layout">
        <aside className="col col--left">
          <section className="panel">
            <p className="eyebrow">Current task</p>
            <h3>Support request</h3>
            <p className="task-copy">{CUSTOMER}</p>
            <table className="mini-table">
              <tbody>
                <tr>
                  <td>Prompt hash</td>
                  <td className="mono">shared V1/V3</td>
                </tr>
                <tr>
                  <td>Fault</td>
                  <td>CommitThenDisconnect</td>
                </tr>
                <tr>
                  <td>Authority</td>
                  <td>Python runtime (not LLM)</td>
                </tr>
              </tbody>
            </table>
          </section>

          <section className="panel panel--scroll">
            <p className="eyebrow">Execution trace</p>
            <ul className="timeline">
              {timeline.map((e) => (
                <li key={`${e.run_id}-${e.seq}`}>
                  <span className="mono seq">{e.seq}</span>
                  <span className="etype">{e.type}</span>
                </li>
              ))}
              {!timeline.length && <li className="muted">Waiting for events…</li>}
            </ul>
          </section>
        </aside>

        <main className="col col--center">
          <InterceptPanel {...intercept} />
        </main>

        <aside className="col col--right">
          <section className="panel">
            <p className="eyebrow">You.com research</p>
            <h3>Capability evidence</h3>
            {research.length === 0 && <p className="muted">No research events yet.</p>}
            {research.map((e) => {
              const caps = (e.payload.capabilities || {}) as Record<string, unknown>;
              const evidence = (caps.evidence || {}) as Record<string, unknown>;
              const citations = (evidence.citations || []) as Array<Record<string, string>>;
              return (
                <div key={`${e.seq}-r`} className="research-block">
                  <div className="chip-row">
                    <span className="chip">{String(e.payload.source || caps.source || "?")}</span>
                    <span className="chip">{String(e.payload.tool_id || "")}</span>
                  </div>
                  <div className="citations">
                    {citations.slice(0, 3).map((c, i) => (
                      <a key={i} href={c.url} target="_blank" rel="noreferrer">
                        {c.title || c.url}
                      </a>
                    ))}
                  </div>
                </div>
              );
            })}
          </section>

          <section className="panel">
            <p className="eyebrow">Learned policy</p>
            <h3>Candidate artifact</h3>
            {policies.length === 0 && <p className="muted">No policy.generated yet.</p>}
            {policies.slice(-2).map((e) => (
              <pre key={e.seq} className="json">
                {JSON.stringify(e.payload.policy, null, 2)}
              </pre>
            ))}
          </section>

          <section className="panel">
            <p className="eyebrow">Daytona / harness</p>
            <h3>Qualification</h3>
            {evals.length === 0 && <p className="muted">No eval events yet.</p>}
            {evals.map((e) => {
              const m = (e.payload.metrics || {}) as Record<string, unknown>;
              return (
                <div key={e.seq} className="eval-row">
                  <strong>
                    v{String(e.payload.version)}{" "}
                    {e.type === "candidate.promoted" ? "PROMOTED" : "REJECTED"}
                  </strong>
                  <ul>
                    <li>safety {String(m.safety_cases_passed)}</li>
                    <li>neg controls {String(m.negative_controls_passed)}</li>
                    <li>verdicts {String(m.verdict_correctness)}</li>
                    <li>unnecessary verifs {String(m.unnecessary_verification_operations)}</li>
                    <li>extra tool ops {String(m.additional_tool_operations)}</li>
                    <li>via {String(m.executed_in)}</li>
                  </ul>
                </div>
              );
            })}
          </section>
        </aside>
      </div>

      <footer className="bottom">
        <section className="panel flat">
          <p className="eyebrow">External state</p>
          <div className="ext-grid">
            <div>
              <h4>Stripe</h4>
              <pre className="json">
                {JSON.stringify(
                  publicState.stripe ||
                    external.find((e) => e.payload.stripe)?.payload.stripe ||
                    {},
                  null,
                  2,
                )}
              </pre>
            </div>
            <div>
              <h4>Linear frozen</h4>
              <pre className="json">
                {JSON.stringify(publicState.linear_frozen || {}, null, 2)}
              </pre>
            </div>
            <div>
              <h4>Linear repaired</h4>
              <pre className="json">
                {JSON.stringify(publicState.linear_repaired || {}, null, 2)}
              </pre>
            </div>
          </div>
        </section>
        <section className="panel flat compare">
          <p className="eyebrow">Invariant</p>
          <h3>V1 vs V3 — same model / prompt / tools / fault</h3>
          <p>
            The only meaningful behavioral difference is the promoted runtime policy.
            Frozen path allows uncorrelated replay. Repaired path blocks it and verifies
            by <code>REPAIR_OP_ID</code> before One.
          </p>
        </section>
      </footer>
    </div>
  );
}
