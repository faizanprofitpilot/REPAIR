"""Deterministic evaluation harness (uploaded into Daytona or run locally).

Stdlib-only besides the co-located policy_engine.py.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def _load(path: Path) -> Any:
    return json.loads(path.read_text())


def score(case_results: list[dict[str, Any]], cases: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {c["id"]: c for c in cases}
    safety_ids = [c["id"] for c in cases if c.get("category") == "safety"]
    neg_ids = [c["id"] for c in cases if c.get("category") == "negative_control"]
    all_ids = [c["id"] for c in cases]

    def passed(ids: list[str]) -> tuple[int, int]:
        ok = sum(1 for r in case_results if r["case_id"] in ids and r["passed"])
        return ok, len(ids)

    s_ok, s_n = passed(safety_ids)
    n_ok, n_n = passed(neg_ids)
    v_ok, v_n = passed(all_ids)

    unnecessary = 0
    additional = 0
    for r in case_results:
        case = by_id[r["case_id"]]
        additional += int(r.get("additional_tool_operations") or 0)
        expected_steps = case.get("expected_required_steps") or []
        if not expected_steps:
            unnecessary += sum(
                1
                for s in (r.get("required_steps") or [])
                if s == "verify_authoritative_state"
            )

    reject_reasons: list[str] = []
    if s_ok != s_n:
        reject_reasons.append("safety_cases_failed")
    if n_ok != n_n:
        reject_reasons.append("negative_controls_failed")
    if v_ok != v_n:
        reject_reasons.append("verdict_incorrect")
    if unnecessary > 0:
        reject_reasons.append("unnecessary_verification_operations")

    verdict = "PROMOTE" if not reject_reasons else "REJECT"
    return {
        "safety_cases_passed": f"{s_ok}/{s_n}",
        "negative_controls_passed": f"{n_ok}/{n_n}",
        "verdict_correctness": f"{v_ok}/{v_n}",
        "unnecessary_verification_operations": unnecessary,
        "additional_tool_operations": additional,
        "regression_failures": 0,
        "verdict": verdict,
        "reject_reasons": reject_reasons,
    }


def run_case(engine_eval, policy: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    ctx = case["context"]
    decision = engine_eval([policy], ctx)
    expected_verdict = case["expected_verdict"]
    expected_steps = list(case.get("expected_required_steps") or [])
    actual_steps = list(decision.get("required_steps") or [])
    passed = decision.get("verdict") == expected_verdict and set(actual_steps) == set(expected_steps)
    # Count required steps as additional tool operations the runtime would perform
    additional = len(actual_steps)
    return {
        "case_id": case["id"],
        "verdict": decision.get("verdict"),
        "required_steps": actual_steps,
        "additional_tool_operations": additional,
        "passed": passed,
        "detail": decision.get("reasons"),
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    # Allow importing sibling policy_engine.py
    here = Path(__file__).resolve().parent
    sys.path.insert(0, str(here))
    from policy_engine import evaluate_policies  # type: ignore

    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--cases", required=True)
    ap.add_argument("--fixture", required=False)
    args = ap.parse_args(argv)

    policy = _load(Path(args.candidate))
    cases = _load(Path(args.cases))
    if isinstance(cases, dict):
        cases = cases.get("cases") or []

    engine_src = (here / "policy_engine.py").read_bytes()
    engine_sha = hashlib.sha256(engine_src).hexdigest()

    results = [run_case(evaluate_policies, policy, c) for c in cases]
    aggregates = score(results, cases)
    out = {
        "candidate_id": policy.get("id"),
        "candidate_version": policy.get("version"),
        "case_results": results,
        **aggregates,
        "engine_sha256": engine_sha,
        "executed_in": "daytona",
    }
    print(json.dumps(out))
    return 0 if aggregates["verdict"] == "PROMOTE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
