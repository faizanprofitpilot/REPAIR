"use client";

import { shortId, type ProofRow } from "@/lib/events";

export function LiveExecutionProof({
  rows,
  runId,
  live,
}: {
  rows: ProofRow[];
  runId: string | null;
  live: boolean;
}) {
  const latestSeq = rows.length ? rows[rows.length - 1].seq : 0;

  return (
    <section className="proof" aria-label="What just ran">
      <header className="proof__head">
        <div className="proof__title">
          <span className="proof__label">What just ran</span>
          <span className="proof__sublabel">Live execution</span>
          <span className={`proof__live ${live ? "is-live" : ""}`}>
            <span className="proof__dot" />
            {live ? "LIVE" : "IDLE"}
          </span>
        </div>
        <div className="proof__meta mono">
          <span>run {runId ? shortId(runId, "run") : "—"}</span>
          <span>seq {String(latestSeq).padStart(3, "0")}</span>
        </div>
      </header>

      <ul className="proof__rows">
        {rows.length === 0 && (
          <li className="proof__row proof__row--empty">
            <span className="proof__ts mono">--:--:--</span>
            <span className="proof__actor">—</span>
            <span className="proof__text">Waiting for backend events…</span>
          </li>
        )}
        {rows.map((r) => (
          <li
            key={r.key}
            className={`proof__row tone-${r.tone || "neutral"} ${r.live ? "is-provider-live" : ""}`}
          >
            <span className="proof__ts mono">{r.ts}</span>
            <span className={`proof__actor actor-${r.actor.replace(".", "")}`}>{r.actor}</span>
            <span className="proof__text">{r.text}</span>
            {r.evidence && <span className="proof__evidence mono">{r.evidence}</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}
