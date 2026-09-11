"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  deriveModel,
  deriveProofRows,
  ENGINE_URL,
  EVENT_TYPES,
  type RepairEvent,
} from "@/lib/events";
import { StageRail } from "@/components/StageRail";
import { DecisionCanvas } from "@/components/DecisionCanvas";
import { ContextCard } from "@/components/ContextCard";
import { WorldState } from "@/components/WorldState";
import { LiveExecutionProof } from "@/components/LiveExecutionProof";
import { SponsorStrip } from "@/components/SponsorStrip";
import { FinalHero } from "@/components/FinalHero";
import { EvidenceDrawer } from "@/components/EvidenceDrawer";

type PublicState = {
  fault_active?: boolean;
  fault_detail?: string | null;
  registry_version?: string;
  phase?: string;
  demo_run_id?: string | null;
  stripe?: unknown;
  linear_frozen?: unknown;
  linear_repaired?: unknown;
};

export default function Home() {
  const [events, setEvents] = useState<RepairEvent[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [publicState, setPublicState] = useState<PublicState>({});
  const [heroDismissed, setHeroDismissed] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  const m = useMemo(() => deriveModel(events), [events]);
  const proofRows = useMemo(() => deriveProofRows(events), [events]);

  // Recording reliability: "running" is derived from run.completed / run.failed,
  // not from the POST returning.
  const running = starting || (runId !== null && !m.runDone);

  const refreshState = useCallback(async () => {
    try {
      const res = await fetch(`${ENGINE_URL}/state`);
      if (res.ok) setPublicState(await res.json());
    } catch {
      /* engine may be down */
    }
  }, []);

  useEffect(() => {
    const first = setTimeout(refreshState, 0);
    const t = setInterval(refreshState, 2000);
    return () => {
      clearTimeout(first);
      clearInterval(t);
    };
  }, [refreshState]);

  const attachSSE = useCallback((id: string) => {
    esRef.current?.close();
    setEvents([]);
    const es = new EventSource(`${ENGINE_URL}/events?run_id=${encodeURIComponent(id)}`);
    esRef.current = es;
    const push = (msg: Event) => {
      try {
        const parsed = JSON.parse((msg as MessageEvent).data) as RepairEvent;
        setEvents((prev) => {
          if (prev.some((p) => p.seq === parsed.seq && p.run_id === parsed.run_id)) return prev;
          return [...prev, parsed].sort((a, b) => a.seq - b.seq);
        });
      } catch {
        /* ignore malformed frames */
      }
    };
    es.onmessage = push;
    for (const t of EVENT_TYPES) es.addEventListener(t, push);
    es.onerror = () => {
      /* keep open; EventSource retries */
    };
  }, []);

  const startDemo = async (phases?: string) => {
    if (running) return; // prevent double start
    setStarting(true);
    setError(null);
    setHeroDismissed(false);
    try {
      const qs = phases ? `?phases=${encodeURIComponent(phases)}` : "";
      const res = await fetch(`${ENGINE_URL}/demo/run${qs}`, { method: "POST" });
      const body = await res.json();
      if (!res.ok) {
        setError(body.error === "demo_already_running" ? "A demo is already running." : body.error || `HTTP ${res.status}`);
        return;
      }
      setRunId(body.run_id);
      attachSSE(body.run_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setStarting(false);
    }
  };

  const faultActive = Boolean(publicState.fault_active) || m.faultActive;
  const ruleLabel = m.ruleInstalled
    ? `Policy: active · v${m.promotedVersion ?? 3}`
    : publicState.registry_version && publicState.registry_version !== "V1" && m.act === 0
      ? `Policy: active · ${publicState.registry_version}`
      : "Policy: none";

  const showHero = m.finalHero && !heroDismissed;

  return (
    <main className="stage">
      <header className="top">
        <div className="brand">
          <span className="brand__mark">REPAIR</span>
          <span className="brand__tag">Memory → policy. Advice → enforcement.</span>
        </div>
        <div className="top__status">
          <span className={`chip ${faultActive ? "chip--amber" : ""}`}>
            {faultActive ? "Transport failure simulated — success hidden from agent" : "Fault ready"}
          </span>
          <span className={`chip ${m.ruleInstalled ? "chip--rule" : ""}`}>{ruleLabel}</span>
        </div>
        <div className="top__actions">
          <button className="btn" onClick={() => startDemo()} disabled={running}>
            {running ? "Playing…" : "Play full story"}
          </button>
          <button
            className="btn btn--ghost"
            onClick={() => startDemo("linear_frozen,linear_repaired")}
            disabled={running}
            title="Requires a promoted rule in the registry"
          >
            Transfer climax only
          </button>
        </div>
      </header>

      <StageRail stage={m.stage} done={m.stagesDone} started={m.act > 0} />

      {error && <div className="error">{error}</div>}
      {m.runFailed && <div className="error">Run failed: {m.runFailed}</div>}

      <div className="grid">
        <DecisionCanvas m={m} />
        <ContextCard m={m} />
      </div>

      <WorldState m={m} />

      <LiveExecutionProof rows={proofRows} runId={runId} live={running} />

      <footer className="foot">
        <SponsorStrip m={m} />
        <EvidenceDrawer m={m} events={events} runId={runId} publicState={publicState as Record<string, unknown>} />
      </footer>

      {showHero && <FinalHero m={m} onDismiss={() => setHeroDismissed(true)} />}
    </main>
  );
}
