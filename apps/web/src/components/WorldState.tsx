"use client";

import { money, shortId, type DemoModel } from "@/lib/events";

export function WorldState({ m }: { m: DemoModel }) {
  const s = m.stripe;
  const l = m.linear;
  const stripeActive = m.domain === "stripe";
  const linearActive = m.domain === "linear";

  const linearShown = linearActive
    ? l.liveCount
    : l.repairedCount ?? l.frozenCount ?? 0;

  const refundIds = s.refundIds || [];

  return (
    <section className="world world--compact">
      <div className={`world__card ${stripeActive ? "is-active" : ""} ${s.duplicate ? "is-duplicate" : ""}`}>
        <div className="world__head">
          <div>
            <span className="eyebrow">What actually happened · Stripe</span>
            <span className="world__sub">external system state · via One</span>
          </div>
        </div>
        <div className="world__numbers world__numbers--compact">
          <div className="metric">
            <span className="metric__label">Refunds</span>
            <span className="metric__value" key={`rc-${s.refundCount}`}>{s.refundCount}</span>
          </div>
          <div className="metric">
            <span className="metric__label">Authorized</span>
            <span className="metric__value metric__value--sm">{money(s.authorizedCents)}</span>
          </div>
          <div className="metric">
            <span className="metric__label">Actually refunded</span>
            <span
              className={`metric__value metric__value--sm ${s.refundedCents > s.authorizedCents ? "is-over" : ""}`}
              key={`rf-${s.refundedCents}`}
            >
              {money(s.refundedCents)}
            </span>
          </div>
        </div>
        <div className={`world__status ${s.duplicate ? "world__status--bad" : ""}`}>
          {s.duplicate
            ? "CUSTOMER REFUNDED TWICE · duplicate side effect"
            : s.refundCount === 1
              ? "One refund committed"
              : "No refunds yet"}
        </div>
        {refundIds.length === 1 && (
          <p className="world__evidence">
            Latest · <strong>{shortId(refundIds[0], "refund")}</strong> · Stripe TEST · via One
          </p>
        )}
        {refundIds.length > 1 && (
          <p className="world__evidence">
            Refunds ·{" "}
            {refundIds.map((id, i) => (
              <span key={id}>
                {i > 0 ? " · " : ""}
                <strong>{shortId(id, "refund")}</strong>
              </span>
            ))}
          </p>
        )}
      </div>

      <div
        className={`world__card ${linearActive ? "is-active" : ""} ${l.prevented ? "is-prevented" : ""} ${
          linearActive && m.controlRun && linearShown >= 2 ? "is-duplicate" : ""
        }`}
      >
        <div className="world__head">
          <div>
            <span className="eyebrow">What actually happened · Linear</span>
            <span className="world__sub">external system state · via One</span>
          </div>
        </div>
        <div className="world__numbers world__numbers--compact">
          <div className="metric">
            <span className="metric__label">Issues created</span>
            <span className="metric__value" key={`li-${linearShown}-${m.controlRun}`}>{linearShown}</span>
          </div>
          <div className="metric">
            <span className="metric__label">Before learning</span>
            <span className="metric__value metric__value--sm">{l.frozenCount ?? "—"}</span>
            <span className="metric__hint">V1 · no rule installed</span>
          </div>
          <div className="metric">
            <span className="metric__label">After learning</span>
            <span className={`metric__value metric__value--sm ${l.repairedCount === 1 ? "is-good" : ""}`}>
              {l.repairedCount ?? "—"}
            </span>
            <span className="metric__hint">V3 · learned rule active</span>
          </div>
        </div>
        <div
          className={`world__status ${
            l.prevented
              ? "world__status--good"
              : linearActive && m.controlRun && linearShown >= 2
                ? "world__status--bad"
                : ""
          }`}
        >
          {l.prevented
            ? "DUPLICATE PREVENTED — one issue, verified"
            : linearActive && m.controlRun && linearShown >= 2
              ? "CUSTOMER ESCALATED TWICE · duplicate side effect"
              : linearActive
                ? m.controlRun
                  ? "Same situation, no safety rule yet"
                  : "After learning · rule active"
                : "Awaiting transfer"}
        </div>
        {(l.latestIdentifier || m.verifiedRef) && (
          <p className="world__evidence">
            Issue · <strong>{l.latestIdentifier || m.verifiedRef}</strong> · via One
          </p>
        )}
      </div>
    </section>
  );
}
