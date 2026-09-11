"use client";

import { money, shortId, type DemoModel } from "@/lib/events";

export function FinalHero({ m, onDismiss }: { m: DemoModel; onDismiss: () => void }) {
  const liveSearches = m.research.filter((r) => r.source === "live");
  const searchSample = liveSearches[0]?.search_uuid || m.research[0]?.search_uuid;
  const rejected = m.gates.find((g) => g.verdict === "REJECTED");
  const promoted = [...m.gates].reverse().find((g) => g.verdict === "PROMOTED");
  const sandboxId = promoted?.sandbox_id || rejected?.sandbox_id;
  const model = m.diagnosis?.model || "gpt-4.1";

  return (
    <div className="hero" role="dialog" aria-label="Result">
      <div className="hero__inner">
        <p className="eyebrow">Result</p>
        <h1 className="hero__title">DUPLICATE PREVENTED</h1>
        <p className="hero__invariant">Same agent. Same prompt. Different runtime rule.</p>

        <div className="hero__compare">
          <div className="hero__col">
            <p className="eyebrow">Before learning</p>
            <p className="hero__stat">
              Stripe · <strong>{m.stripe.refundCount || 2}</strong> refunds ·{" "}
              <strong>{money(m.stripe.refundedCents || 2580)}</strong>
            </p>
            <p className="hero__muted">Authorized: {money(m.stripe.authorizedCents || 1290)}</p>
            <p className="hero__stat">
              Linear · <strong>{m.linear.frozenCount ?? 2}</strong> issues
            </p>
          </div>
          <div className="hero__col hero__col--after">
            <p className="eyebrow">After learning</p>
            <p className="hero__stat">
              Linear · <strong>{m.linear.repairedCount ?? 1}</strong> issue
            </p>
            {m.verifiedRef && (
              <p className="hero__muted">existing {m.verifiedRef} verified</p>
            )}
            <p className="hero__never">NEVER SENT TO ONE</p>
          </div>
        </div>

        <div className="hero__sponsors">
          <div className="hero__sponsor">
            <p className="hero__sponsor-name">One</p>
            <p>Real Stripe + Linear actions</p>
            <p className="hero__muted">Blocked replay never dispatched</p>
          </div>
          <div className="hero__sponsor">
            <p className="hero__sponsor-name">You.com</p>
            <p>Live first-party research</p>
            <p className="hero__muted mono">
              {liveSearches.length || m.research.length} live search
              {(liveSearches.length || m.research.length) === 1 ? "" : "es"}
              {searchSample ? ` · ${shortId(searchSample, "uuid")}` : ""}
            </p>
          </div>
          <div className="hero__sponsor">
            <p className="hero__sponsor-name">CrewAI</p>
            <p>Live adaptation</p>
            <p className="hero__muted">Diagnosed + synthesized · {model}</p>
          </div>
          <div className="hero__sponsor">
            <p className="hero__sponsor-name">Daytona</p>
            <p>
              V{rejected?.version ?? 2} rejected → V{promoted?.version ?? m.promotedVersion ?? 3}{" "}
              approved
            </p>
            <p className="hero__muted mono">
              {sandboxId
                ? `sandbox ${shortId(sandboxId, "uuid")} · audit logged`
                : "Qualified in an ephemeral Daytona sandbox"}
            </p>
          </div>
        </div>

        <p className="hero__thesis">
          It didn’t learn the answer.
          <br />
          <strong>It changed how it operates.</strong>
        </p>

        <button type="button" className="btn btn--ghost hero__dismiss" onClick={onDismiss}>
          Show evidence
        </button>
      </div>
    </div>
  );
}
