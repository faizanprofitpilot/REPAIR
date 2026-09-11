"use client";

import { STAGES, type Stage } from "@/lib/events";

const LABELS: Record<Stage, string> = {
  EXECUTE: "Execute",
  FAIL: "Fail",
  DIAGNOSE: "Diagnose",
  RESEARCH: "Research",
  SYNTHESIZE: "Synthesize",
  TEST: "Test",
  PROMOTE: "Promote",
  ENFORCE: "Enforce",
  TRANSFER: "Transfer",
};

const ACT: Record<Stage, string> = {
  EXECUTE: "Act 1 · Fail",
  FAIL: "Act 1 · Fail",
  DIAGNOSE: "Act 2 · Learn",
  RESEARCH: "Act 2 · Learn",
  SYNTHESIZE: "Act 2 · Learn",
  TEST: "Act 2 · Learn",
  PROMOTE: "Act 2 · Learn",
  ENFORCE: "Act 3 · Enforce",
  TRANSFER: "Act 3 · Transfer",
};

export function StageRail({
  stage,
  done,
  started,
}: {
  stage: Stage;
  done: Set<Stage>;
  started: boolean;
}) {
  return (
    <nav className="rail" aria-label="Demo stages">
      <span className="rail__act">{started ? ACT[stage] : "Ready"}</span>
      <ol className="rail__list">
        {STAGES.map((s, i) => {
          const isActive = started && s === stage;
          const isDone = started && done.has(s) && s !== stage;
          return (
            <li
              key={s}
              className={`rail__step ${isActive ? "is-active" : ""} ${isDone ? "is-done" : ""}`}
            >
              <span className="rail__dot" />
              <span className="rail__label">{LABELS[s]}</span>
              {i < STAGES.length - 1 && <span className="rail__arrow">→</span>}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
