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

type Act = 0 | 1 | 2 | 3 | 4;

const ACTS: Array<{
  act: 1 | 2 | 3 | 4;
  phases: string;
  label: string;
  runningLabel: string;
  hint: string;
  stepName: string;
}> = [
  {
    act: 1,
    phases: "stripe_frozen",
    label: "SHOW THE FAILURE",
    runningLabel: "RUNNING FAILURE…",
    hint: "Let the agent handle a real Stripe test refund.",
    stepName: "FAILURE",
  },
  {
    act: 2,
    phases: "learn",
    label: "LEARN FROM THIS FAILURE",
    runningLabel: "LEARNING…",
    hint: "Turn the failure into a tested runtime rule.",
    stepName: "LEARN",
  },
  {
    act: 3,
    phases: "linear_frozen",
    label: "RUN WITHOUT THE LEARNED RULE",
    runningLabel: "RUNNING CONTROL…",
    hint: "Same agent. Same fault. No learned protection.",
    stepName: "CONTROL",
  },
  {
    act: 4,
    phases: "linear_repaired",
    label: "RUN WITH THE LEARNED RULE",
    runningLabel: "RUNNING WITH RULE…",
    hint: "Same agent. Same fault. Learned rule active.",
    stepName: "ENFORCE",
  },
];

const PHASE_SCENARIOS = new Set(["stripe_incident", "learning_loop", "linear_holdout"]);

function activeRunStatus(
  events: RepairEvent[],
  activeRunId: string | null,
): "idle" | "running" | "completed" | "failed" {
  if (!activeRunId) return "idle";
  const related = events.filter((e) => e.run_id === activeRunId);
  if (related.some((e) => e.type === "run.failed")) return "failed";
  if (related.some((e) => e.type === "run.completed")) return "completed";
  return "running";
}

function scenarioAct(scenario: unknown, frozen: unknown): Act | null {
  if (scenario === "stripe_incident") return 1;
  if (scenario === "learning_loop") return 2;
  if (scenario === "linear_holdout" && frozen === true) return 3;
  if (scenario === "linear_holdout" && frozen === false) return 4;
  return null;
}

function deriveCompletedActs(events: RepairEvent[]): Set<number> {
  const done = new Set<number>();
  const byRun = new Map<string, RepairEvent[]>();
  for (const e of events) {
    const list = byRun.get(e.run_id) || [];
    list.push(e);
    byRun.set(e.run_id, list);
  }
  for (const [, evs] of byRun) {
    if (!evs.some((e) => e.type === "run.completed")) continue;
    const start = evs.find(
      (e) => e.type === "run.started" && PHASE_SCENARIOS.has(String(e.payload?.scenario ?? "")),
    );
    if (start) {
      const act = scenarioAct(start.payload?.scenario, start.payload?.frozen);
      if (act) done.add(act);
      continue;
    }
    if (evs.some((e) => e.type === "run.started" && e.payload?.scenario === "full_demo")) {
      done.add(1);
      done.add(2);
      done.add(3);
      done.add(4);
    }
  }
  return done;
}

export default function Home() {
  const [sessionEvents, setSessionEvents] = useState<RepairEvent[]>([]);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [currentAct, setCurrentAct] = useState<Act>(0);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [publicState, setPublicState] = useState<PublicState>({});
  const [heroDismissed, setHeroDismissed] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  const m = useMemo(() => deriveModel(sessionEvents), [sessionEvents]);
  const proofRows = useMemo(() => deriveProofRows(sessionEvents), [sessionEvents]);
  const completedActs = useMemo(() => deriveCompletedActs(sessionEvents), [sessionEvents]);

  const runStatus = activeRunStatus(sessionEvents, activeRunId);
  const running = starting || runStatus === "running";
  const actFailed = runStatus === "failed";

  const displayAct: Act = useMemo(() => {
    if (activeRunId) {
      const start = sessionEvents.find(
        (e) =>
          e.run_id === activeRunId &&
          e.type === "run.started" &&
          PHASE_SCENARIOS.has(String(e.payload?.scenario ?? "")),
      );
      const act = scenarioAct(start?.payload?.scenario, start?.payload?.frozen);
      if (act) return act;
    }
    return currentAct;
  }, [activeRunId, sessionEvents, currentAct]);

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
    // Do NOT clear sessionEvents — accumulate across acts.
    const es = new EventSource(`${ENGINE_URL}/events?run_id=${encodeURIComponent(id)}`);
    esRef.current = es;
    const push = (msg: Event) => {
      try {
        const parsed = JSON.parse((msg as MessageEvent).data) as RepairEvent;
        setSessionEvents((prev) => {
          if (prev.some((p) => p.run_id === parsed.run_id && p.seq === parsed.seq)) return prev;
          // Append only — never sort by seq alone (seqs restart per run_id).
          return [...prev, parsed];
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

  const nextActNum = ([1, 2, 3, 4] as const).find((n) => !completedActs.has(n)) ?? 4;
  const waitingToStart = !running && !actFailed && completedActs.size < 4;
  const retrying = actFailed && displayAct >= 1 && displayAct <= 4;

  const ctaDef = (() => {
    if (running && displayAct >= 1 && displayAct <= 4) return ACTS[displayAct - 1];
    if (retrying) return ACTS[displayAct - 1];
    if (waitingToStart) return ACTS[nextActNum - 1];
    return null;
  })();

  const startAct = async (act: 1 | 2 | 3 | 4) => {
    if (running) return;
    const def = ACTS[act - 1];
    setStarting(true);
    setError(null);
    setHeroDismissed(false);
    // On retry, drop only the failed active run's events (keep prior acts).
    if (actFailed && activeRunId) {
      const failedId = activeRunId;
      setSessionEvents((prev) => prev.filter((e) => e.run_id !== failedId));
    }
    setCurrentAct(act);
    try {
      const res = await fetch(
        `${ENGINE_URL}/demo/run?phases=${encodeURIComponent(def.phases)}`,
        { method: "POST" },
      );
      const body = await res.json();
      if (!res.ok) {
        setError(
          body.error === "demo_already_running"
            ? "A demo is already running."
            : body.error || `HTTP ${res.status}`,
        );
        return;
      }
      setActiveRunId(body.run_id);
      attachSSE(body.run_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setStarting(false);
    }
  };

  const startFullStoryFallback = async () => {
    if (running) return;
    setStarting(true);
    setError(null);
    setHeroDismissed(false);
    setCurrentAct(0);
    setSessionEvents([]);
    try {
      const res = await fetch(`${ENGINE_URL}/demo/run`, { method: "POST" });
      const body = await res.json();
      if (!res.ok) {
        setError(
          body.error === "demo_already_running"
            ? "A demo is already running."
            : body.error || `HTTP ${res.status}`,
        );
        return;
      }
      setActiveRunId(body.run_id);
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
    : completedActs.has(2)
      ? "Policy: learned · not applied this step"
      : publicState.registry_version && publicState.registry_version !== "V1" && displayAct === 0
        ? `Policy: active · ${publicState.registry_version}`
        : "Policy: none";

  // FinalHero ONLY after Act 4 success with enforcement climax.
  const showHero =
    completedActs.has(4) &&
    m.climaxReached &&
    m.linear.prevented &&
    !heroDismissed &&
    !running;

  const stepEyebrow = (() => {
    if (running && displayAct >= 1) {
      return `LEARNING LOOP · ACT ${displayAct} · ${ACTS[displayAct - 1].stepName}`;
    }
    if (completedActs.size >= 4) return "LEARNING LOOP · 4 OF 4 COMPLETE";
    if (actFailed) return `LEARNING LOOP · ACT ${displayAct} FAILED`;
    if (completedActs.size === 0) return "LEARNING LOOP · 1 OF 4";
    return `LEARNING LOOP · ${completedActs.size} OF 4 COMPLETE`;
  })();

  const ctaLabel = (() => {
    if (running && displayAct >= 1) return ACTS[displayAct - 1].runningLabel;
    if (retrying) return `RETRY: ${ACTS[displayAct - 1].label}`;
    return ctaDef?.label ?? null;
  })();

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
          <span className={`chip ${m.ruleInstalled || completedActs.has(2) ? "chip--rule" : ""}`}>
            {ruleLabel}
          </span>
        </div>
        <div className="top__actions top__actions--paced">
          <div className="act-cta">
            <p className="act-cta__eyebrow">{stepEyebrow}</p>
            {ctaLabel && ctaDef && (
              <>
                <button
                  className="btn"
                  disabled={running}
                  onClick={() =>
                    startAct(
                      retrying || running
                        ? (displayAct as 1 | 2 | 3 | 4)
                        : ctaDef.act,
                    )
                  }
                >
                  {ctaLabel}
                </button>
                <p className="act-cta__hint">
                  {retrying
                    ? "Previous evidence kept. Retry this step only."
                    : ctaDef.hint}
                </p>
              </>
            )}
            {!ctaLabel && completedActs.has(4) && (
              <p className="act-cta__hint">Session complete — duplicate prevented.</p>
            )}
          </div>
          <button
            type="button"
            className="btn-debug"
            onClick={() => startFullStoryFallback()}
            disabled={running}
            title="Run all phases in one request"
          >
            Run all phases
          </button>
        </div>
      </header>

      <div className="act-indicator">
        {[1, 2, 3, 4].map((n) => {
          const names = ["FAILURE", "LEARN", "CONTROL", "ENFORCE"];
          const done = completedActs.has(n);
          const active = displayAct === n && (running || actFailed);
          return (
            <span
              key={n}
              className={`act-indicator__item ${done ? "is-done" : ""} ${active ? "is-active" : ""}`}
            >
              ACT {n} · {names[n - 1]}
            </span>
          );
        })}
      </div>

      <StageRail stage={m.stage} done={m.stagesDone} started={sessionEvents.length > 0} />

      {error && <div className="error">{error}</div>}
      {actFailed && (
        <div className="error">
          Act {displayAct} failed
          {m.runFailed ? `: ${m.runFailed}` : ""}. Previous evidence kept.
        </div>
      )}

      <div className="grid">
        <DecisionCanvas m={m} />
        <ContextCard m={m} />
      </div>

      <LiveExecutionProof rows={proofRows} runId={activeRunId} live={running} />

      <WorldState m={m} />

      <footer className="foot">
        <SponsorStrip m={m} />
        <EvidenceDrawer
          m={m}
          events={sessionEvents}
          runId={activeRunId}
          publicState={publicState as Record<string, unknown>}
        />
      </footer>

      {showHero && <FinalHero m={m} onDismiss={() => setHeroDismissed(true)} />}
    </main>
  );
}
