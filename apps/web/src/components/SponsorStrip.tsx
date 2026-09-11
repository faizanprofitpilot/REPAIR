"use client";

import type { DemoModel, SponsorKey } from "@/lib/events";

const ROLES: Array<{ key: SponsorKey; name: string; role: string }> = [
  { key: "one", name: "One", role: "real actions" },
  { key: "youcom", name: "You.com", role: "live evidence" },
  { key: "crewai", name: "CrewAI", role: "adaptation" },
  { key: "daytona", name: "Daytona", role: "qualification" },
];

export function SponsorStrip({ m, allDone = false }: { m: DemoModel; allDone?: boolean }) {
  return (
    <div className="sponsors">
      {ROLES.map((r) => {
        const s = m.sponsors[r.key];
        const status = allDone ? "done" : s.status;
        return (
          <div key={r.key} className={`sponsor sponsor--${status}`}>
            <span className="sponsor__dot" />
            <span className="sponsor__name">{r.name}</span>
            <span className="sponsor__role">— {r.role}</span>
            {status !== "idle" && s.note && !allDone && <span className="sponsor__note">{s.note}</span>}
          </div>
        );
      })}
    </div>
  );
}
