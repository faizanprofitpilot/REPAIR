"use client";

import {
  capabilityConclusion,
  humanReject,
  policyBreadth,
  policyToEnglish,
  type DemoModel,
  type GateView,
} from "@/lib/events";

function GateRow({ g }: { g: GateView }) {
  const promoted = g.verdict === "PROMOTED";
  return (
    <div className={`gate ${promoted ? "gate--promote" : "gate--reject"}`} key={`${g.version}-${g.verdict}`}>
      <div className="gate__row">
        <span className="gate__version">V{g.version}</span>
        <span className="gate__stamp">{g.verdict}</span>
      </div>
      <p className="gate__reason">
        {promoted
          ? "Passes every safety case with zero unnecessary verification."
          : `Reason: ${humanReject(g.reasons)}`}
      </p>
      <p className="gate__meta mono">
        executed_in={g.executed_in || "—"}
        {g.sandbox_id ? ` · sandbox ${g.sandbox_id}` : ""}
      </p>
      {g.metrics && (
        <p className="gate__metrics">
          safety {String(g.metrics.safety_cases_passed)} · controls {String(g.metrics.negative_controls_passed)} ·
          verdicts {String(g.metrics.verdict_correctness)} · extra verifications{" "}
          {String(g.metrics.unnecessary_verification_operations)}
        </p>
      )}
    </div>
  );
}

export function ContextCard({ m }: { m: DemoModel }) {
  const stage = m.stage;

  if (m.act === 0) {
    return (
      <aside className="context">
        <p className="eyebrow">What you are about to see</p>
        <h3>An agent that turns a failure into a runtime rule</h3>
        <ol className="context__acts">
          <li><strong>Fail.</strong> A refund commits, the response is lost, the agent retries blindly.</li>
          <li><strong>Learn.</strong> CrewAI diagnoses, You.com researches, Daytona tests candidate rules.</li>
          <li><strong>Enforce.</strong> Same agent in an unseen domain — the runtime blocks the replay.</li>
        </ol>
      </aside>
    );
  }

  if (stage === "EXECUTE" || stage === "FAIL") {
    return (
      <aside className="context">
        <p className="eyebrow">{stage === "FAIL" ? "What went wrong" : "Live action"}</p>
        <h3>{stage === "FAIL" ? "The agent could not tell success from failure" : "Real Stripe test-mode action via One"}</h3>
        <p className="context__body">
          {stage === "FAIL"
            ? "The mutation committed. The response never came back. Without a rule, an ordinary retry is a second mutation."
            : "The support agent reads the order and issues the approved refund through One."}
        </p>
      </aside>
    );
  }

  if (stage === "DIAGNOSE") {
    return (
      <aside className="context context--crewai">
        <p className="eyebrow">CrewAI · adaptation {m.diagnosis?.model ? `· ${m.diagnosis.model}` : ""}</p>
        <h3>Diagnosis</h3>
        {m.diagnosis?.root ? (
          <>
            <p className="context__body">{m.diagnosis.root}</p>
            {m.diagnosis.observed && <p className="context__muted">{m.diagnosis.observed}</p>}
          </>
        ) : (
          <p className="context__muted pulse">Diagnosing the incident…</p>
        )}
      </aside>
    );
  }

  if (stage === "RESEARCH") {
    const r = m.research[m.research.length - 1];
    const cite = r?.citations?.find((c) => c.title) || r?.citations?.[0];
    return (
      <aside className="context context--youcom">
        <p className="eyebrow">
          You.com · live evidence{" "}
          {r && <span className={`badge ${r.source === "live" ? "badge--live" : "badge--cached"}`}>{r.source.toUpperCase()}</span>}
        </p>
        <h3>Research</h3>
        {r ? (
          <>
            {cite && (
              <a className="context__cite" href={cite.url} target="_blank" rel="noreferrer">
                {cite.title || cite.url}
              </a>
            )}
            <p className="context__body">{capabilityConclusion(r)}</p>
            {r.search_uuid && <p className="context__muted mono">search {r.search_uuid}</p>}
          </>
        ) : (
          <p className="context__muted pulse">Querying first-party documentation…</p>
        )}
      </aside>
    );
  }

  if (stage === "SYNTHESIZE") {
    const p = m.policies[m.policies.length - 1];
    return (
      <aside className="context context--crewai">
        <p className="eyebrow">CrewAI · proposed rule {p?.version ? `· v${p.version}` : ""}</p>
        <h3>{p ? "Synthesized rule" : "Synthesizing…"}</h3>
        {p ? (
          <>
            <p className="context__rule">{policyToEnglish(p)}</p>
            <p className="context__muted">
              {policyBreadth(p) === "broad" ? "Broad first draft — applies to every persistent mutation." : "Refined — applies only to ambiguous outcomes."} Domain-free by guard.
            </p>
          </>
        ) : (
          <p className="context__muted pulse">Drafting a domain-free runtime rule…</p>
        )}
      </aside>
    );
  }

  if (stage === "TEST" || stage === "PROMOTE") {
    return (
      <aside className="context context--daytona">
        <p className="eyebrow">Daytona sandbox · qualification</p>
        <h3>{stage === "PROMOTE" ? "Rule promoted" : "Testing candidates"}</h3>
        {m.gates.length === 0 && <p className="context__muted pulse">Running deterministic evaluation in a fresh sandbox…</p>}
        {m.gates.map((g, i) => (
          <GateRow g={g} key={`${g.version}-${g.verdict}-${i}`} />
        ))}
        {m.sponsors.daytona.status === "active" && m.gates.length > 0 && stage === "TEST" && (
          <p className="context__muted pulse">Refining and re-testing…</p>
        )}
      </aside>
    );
  }

  // ENFORCE / TRANSFER
  const promoted = m.policies.find((p) => p.version === m.promotedVersion) || m.policies[m.policies.length - 1];
  const linearResearch = m.research.find((r) => r.tool_id.startsWith("linear"));
  return (
    <aside className="context context--transfer">
      <p className="eyebrow">Unseen domain</p>
      <h3>Linear · engineering escalation</h3>
      <p className="context__body">
        Same agent. Same prompt. {m.ruleInstalled ? "Same learned runtime rule." : "No rule installed — control run."}
      </p>
      {linearResearch && (
        <p className="context__muted">
          <span className={`badge ${linearResearch.source === "live" ? "badge--live" : "badge--cached"}`}>
            YOU.COM {linearResearch.source.toUpperCase()}
          </span>{" "}
          {capabilityConclusion(linearResearch)}
        </p>
      )}
      {m.ruleInstalled && promoted && (
        <>
          <p className="eyebrow" style={{ marginTop: "0.9rem" }}>Installed rule v{promoted.version}</p>
          <p className="context__rule">{policyToEnglish(promoted)}</p>
        </>
      )}
    </aside>
  );
}
