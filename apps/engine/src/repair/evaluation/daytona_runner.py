"""Daytona / local evaluation runner."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from repair.config import REPO_ROOT, get_settings
from repair.events.bus import bus
from repair.models import LearnedPolicy
from repair.runtime.policy_engine import vocabulary_guard


ENGINE_SRC = Path(__file__).resolve().parents[1] / "runtime" / "policy_engine.py"
HARNESS_SRC = Path(__file__).resolve().parent / "harness.py"
CASES = REPO_ROOT / "fixtures" / "eval_cases.json"
ENGINE_ROOT = Path(__file__).resolve().parents[3]  # apps/engine
DAYTONA_SCRIPT = ENGINE_ROOT / "scripts" / "run_daytona_eval.py"
DAYTONA_PYTHON = ENGINE_ROOT / "daytona_runner_env" / ".venv" / "bin" / "python"


def _require_live() -> bool:
    settings = get_settings()
    return bool(settings.daytona_api_key) and os.environ.get("REPAIR_ALLOW_LOCAL_EVAL", "").lower() not in {
        "1",
        "true",
        "yes",
    }


def evaluate_candidate_local(
    policy: LearnedPolicy | dict[str, Any],
    *,
    run_id: str,
    executed_in: str = "local_fallback",
) -> dict[str, Any]:
    policy_dict = policy.model_dump(mode="json") if isinstance(policy, LearnedPolicy) else policy
    ok, hits = vocabulary_guard(policy_dict)
    if not ok:
        bus.emit(run_id, "policy.rejected_by_guard", {"hits": hits})
        return {
            "verdict": "REJECT",
            "reject_reasons": ["vocabulary_guard", *hits],
            "executed_in": executed_in,
            "case_results": [],
        }

    with tempfile.TemporaryDirectory() as tmp:
        tdir = Path(tmp)
        shutil.copy(ENGINE_SRC, tdir / "policy_engine.py")
        shutil.copy(HARNESS_SRC, tdir / "harness.py")
        cand = tdir / "candidate.json"
        cases = tdir / "eval_cases.json"
        cand.write_text(json.dumps(policy_dict))
        shutil.copy(CASES, cases)
        proc = subprocess.run(
            [
                "python3",
                str(tdir / "harness.py"),
                "--candidate",
                str(cand),
                "--cases",
                str(cases),
            ],
            capture_output=True,
            text=True,
            cwd=str(tdir),
        )
        raw = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "{}"
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            result = {
                "verdict": "REJECT",
                "reject_reasons": ["harness_parse_error"],
                "stderr": proc.stderr[-1000:],
            }
        result["executed_in"] = executed_in
        return result


def evaluate_candidate_daytona(
    policy: LearnedPolicy | dict[str, Any],
    *,
    run_id: str,
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.daytona_api_key:
        raise RuntimeError("DAYTONA_API_KEY missing — cannot run live Daytona qualification")

    if not DAYTONA_PYTHON.exists():
        raise RuntimeError(f"Daytona isolated python missing at {DAYTONA_PYTHON}")

    policy_dict = policy.model_dump(mode="json") if isinstance(policy, LearnedPolicy) else policy
    ok, hits = vocabulary_guard(policy_dict)
    if not ok:
        bus.emit(run_id, "policy.rejected_by_guard", {"hits": hits})
        return {
            "verdict": "REJECT",
            "reject_reasons": ["vocabulary_guard", *hits],
            "executed_in": "daytona",
            "case_results": [],
        }

    bus.emit(run_id, "evaluation.started", {"mode": "daytona"})

    with tempfile.TemporaryDirectory() as tmp:
        tdir = Path(tmp)
        cand = tdir / "candidate.json"
        out = tdir / "result.json"
        cand.write_text(json.dumps(policy_dict))
        env = os.environ.copy()
        env["DAYTONA_API_KEY"] = settings.daytona_api_key
        if settings.daytona_api_url:
            env["DAYTONA_API_URL"] = settings.daytona_api_url
        if settings.daytona_target:
            env["DAYTONA_TARGET"] = settings.daytona_target

        proc = subprocess.run(
            [
                str(DAYTONA_PYTHON),
                str(DAYTONA_SCRIPT),
                "--candidate",
                str(cand),
                "--cases",
                str(CASES),
                "--engine",
                str(ENGINE_SRC),
                "--harness",
                str(HARNESS_SRC),
                "--out",
                str(out),
            ],
            capture_output=True,
            text=True,
            env=env,
            timeout=180,
        )
        if out.exists():
            result = json.loads(out.read_text())
        else:
            try:
                result = json.loads(proc.stdout.strip().splitlines()[-1])
            except Exception:
                result = {
                    "verdict": "REJECT",
                    "reject_reasons": ["daytona_subprocess_failed"],
                    "stdout": proc.stdout[-1500:],
                    "stderr": proc.stderr[-1500:],
                    "returncode": proc.returncode,
                    "executed_in": "daytona_failed",
                }

        if result.get("executed_in") != "daytona" or not result.get("sandbox_id"):
            # Do not silently substitute local harness for final qualification
            result.setdefault("executed_in", "daytona_failed")
            result.setdefault("reject_reasons", []).append("daytona_did_not_complete")
            if proc.stderr:
                result["stderr"] = proc.stderr[-1500:]
            bus.emit(
                run_id,
                "evaluation.failed",
                {
                    "mode": "daytona",
                    "error": result.get("daytona_error") or result.get("reject_reasons"),
                    "sandbox_id": result.get("sandbox_id"),
                },
            )
            return result

        bus.emit(
            run_id,
            "evaluation.completed",
            {
                "mode": "daytona",
                "sandbox_id": result.get("sandbox_id"),
                "verdict": result.get("verdict"),
            },
        )
        return result


def evaluate_candidate(
    policy: LearnedPolicy | dict[str, Any],
    *,
    run_id: str,
) -> dict[str, Any]:
    settings = get_settings()
    if settings.daytona_api_key:
        return evaluate_candidate_daytona(policy, run_id=run_id)
    if _require_live():
        raise RuntimeError("DAYTONA_API_KEY required for live qualification")
    return evaluate_candidate_local(policy, run_id=run_id, executed_in="local_fallback")
