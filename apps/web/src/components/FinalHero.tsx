"use client";

import type { DemoModel } from "@/lib/events";
import { SponsorStrip } from "@/components/SponsorStrip";

export function FinalHero({ m, onDismiss }: { m: DemoModel; onDismiss: () => void }) {
  return (
    <div className="hero" role="dialog" aria-label="Result">
      <div className="hero__inner">
        <p className="eyebrow">Result</p>
        <h1 className="hero__title">DUPLICATE PREVENTED</h1>
        <ul className="hero__facts">
          <li>Unsafe replay blocked before execution.</li>
          <li>Existing operation verified{m.verifiedRef ? ` · ${m.verifiedRef}` : ""}.</li>
          <li>
            Issues created: <strong>{m.linear.repairedCount ?? 1}</strong>
            {m.linear.frozenCount ? <span className="hero__muted"> (without rule: {m.linear.frozenCount})</span> : null}
          </li>
        </ul>

        <p className="hero__thesis">
          It didn’t learn the answer.
          <br />
          <strong>It changed how it operates.</strong>
        </p>
        <p className="hero__invariant">
          Same agent. Same prompt. Different runtime rule.
          {m.promptHash && <span className="mono hero__hash"> · prompt {m.promptHash}</span>}
        </p>

        <SponsorStrip m={m} allDone />

        <button type="button" className="btn btn--ghost hero__dismiss" onClick={onDismiss}>
          Show evidence
        </button>
      </div>
    </div>
  );
}
