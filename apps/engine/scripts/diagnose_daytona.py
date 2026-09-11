#!/usr/bin/env python3
"""Step-by-step Daytona diagnostic for REPAIR. No Stripe/Linear mutations."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path


ENGINE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ENGINE_ROOT.parents[1]
DAYTONA_PYTHON = ENGINE_ROOT / "daytona_runner_env" / ".venv" / "bin" / "python"
DAYTONA_SCRIPT = ENGINE_ROOT / "scripts" / "run_daytona_eval.py"
ENGINE_SRC = ENGINE_ROOT / "src" / "repair" / "runtime" / "policy_engine.py"
HARNESS_SRC = ENGINE_ROOT / "src" / "repair" / "evaluation" / "harness.py"
CASES = REPO_ROOT / "fixtures" / "eval_cases.json"
CANDIDATE = REPO_ROOT / "policies" / "candidates" / "v2.json"
ARTIFACT_ROOT = REPO_ROOT / "artifacts" / "daytona-diagnostic"


def _mask_env() -> dict[str, str]:
    env = os.environ.copy()
    # Prefer .env via repair.config when importing production path later
    return env


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env", override=True)
        load_dotenv(ENGINE_ROOT / ".env", override=True)
    except Exception:
        pass


def _write_artifact(ts_dir: Path, name: str, content: str) -> None:
    ts_dir.mkdir(parents=True, exist_ok=True)
    (ts_dir / name).write_text(content)


def _ok(label: str, detail: str = "") -> None:
    print(f"PASS  {label}" + (f" — {detail}" if detail else ""))


def _fail(label: str, detail: str = "") -> None:
    print(f"FAIL  {label}" + (f" — {detail}" if detail else ""))


def step0(ts_dir: Path) -> dict:
    print("\n=== STEP 0 — environment ===")
    report: dict = {"step": 0}
    report["python_executable"] = sys.executable
    report["python_version"] = sys.version
    report["repo_root"] = str(REPO_ROOT)
    report["engine_root"] = str(ENGINE_ROOT)
    report["daytona_python_exists"] = DAYTONA_PYTHON.exists()
    report["daytona_python"] = str(DAYTONA_PYTHON)
    report["DAYTONA_API_KEY_present"] = bool(os.environ.get("DAYTONA_API_KEY"))
    report["DAYTONA_API_URL"] = os.environ.get("DAYTONA_API_URL") or None
    report["DAYTONA_TARGET"] = os.environ.get("DAYTONA_TARGET") or None
    report["engine_src_exists"] = ENGINE_SRC.exists()
    report["harness_exists"] = HARNESS_SRC.exists()
    report["cases_exists"] = CASES.exists()
    report["candidate_exists"] = CANDIDATE.exists()

    print(f"python: {sys.executable}")
    print(f"version: {sys.version.split()[0]}")
    print(f"repo: {REPO_ROOT}")
    print(f"daytona venv python exists: {DAYTONA_PYTHON.exists()}")
    print(f"DAYTONA_API_KEY present: {report['DAYTONA_API_KEY_present']}")
    print(f"DAYTONA_API_URL: {report['DAYTONA_API_URL']}")
    print(f"DAYTONA_TARGET: {report['DAYTONA_TARGET']}")

    if not DAYTONA_PYTHON.exists():
        _fail("daytona isolated venv")
        report["ok"] = False
        return report

    proc = subprocess.run(
        [
            str(DAYTONA_PYTHON),
            "-c",
            "import importlib.metadata as m\n"
            "import daytona\n"
            "try:\n"
            "  v=m.version('daytona')\n"
            "except Exception:\n"
            "  try: v=m.version('daytona-sdk')\n"
            "  except Exception: v='unknown'\n"
            "print(v)\n"
            "from daytona import Daytona, CreateSandboxFromSnapshotParams, FileUpload\n"
            "print('IMPORT_OK')\n",
        ],
        capture_output=True,
        text=True,
        env=_mask_env(),
    )
    _write_artifact(ts_dir, "step0_stdout.txt", proc.stdout)
    _write_artifact(ts_dir, "step0_stderr.txt", proc.stderr)
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    report["daytona_package_version"] = lines[0] if lines else None
    report["import_ok"] = "IMPORT_OK" in proc.stdout
    report["step0_returncode"] = proc.returncode
    if proc.returncode == 0 and report["import_ok"] and report["DAYTONA_API_KEY_present"]:
        _ok("environment", f"daytona=={report['daytona_package_version']}")
        report["ok"] = True
    else:
        _fail("environment", f"rc={proc.returncode} stderr={proc.stderr[-500:]}")
        report["ok"] = False
    return report


def step1(ts_dir: Path) -> dict:
    print("\n=== STEP 1 — SDK compatibility ===")
    code = r"""
import inspect
from daytona import Daytona, CreateSandboxFromSnapshotParams, FileUpload
print("Daytona", Daytona)
print("create", getattr(Daytona, "create", None))
print("delete", getattr(Daytona, "delete", None))
print("CreateSandboxFromSnapshotParams", inspect.signature(CreateSandboxFromSnapshotParams))
print("FileUpload", inspect.signature(FileUpload))
# probe Sandbox methods via annotations if available
from daytona import Sandbox
print("Sandbox.fs", getattr(Sandbox, "fs", None))
print("Sandbox.process", getattr(Sandbox, "process", None))
print("SDK_COMPAT_OK")
"""
    proc = subprocess.run([str(DAYTONA_PYTHON), "-c", code], capture_output=True, text=True, env=_mask_env())
    _write_artifact(ts_dir, "step1_stdout.txt", proc.stdout)
    _write_artifact(ts_dir, "step1_stderr.txt", proc.stderr)
    print(proc.stdout)
    if proc.stderr:
        print("stderr:", proc.stderr[-800:])
    ok = proc.returncode == 0 and "SDK_COMPAT_OK" in proc.stdout
    if ok:
        _ok("SDK compatibility")
    else:
        _fail("SDK compatibility", f"rc={proc.returncode}")
    return {"step": 1, "ok": ok, "stdout": proc.stdout[-2000:], "stderr": proc.stderr[-2000:]}


def step2(ts_dir: Path) -> dict:
    print("\n=== STEP 2 — bare sandbox lifecycle ===")
    code = r"""
import json, traceback
from daytona import Daytona, CreateSandboxFromSnapshotParams
sandbox = None
daytona = Daytona()
try:
    sandbox = daytona.create(CreateSandboxFromSnapshotParams(language="python"))
    sid = getattr(sandbox, "id", None) or getattr(sandbox, "instance_id", None)
    print("SANDBOX_ID", sid)
    print("SANDBOX_TYPE", type(sandbox).__name__)
    resp = sandbox.process.exec("python3 -c \"print('REPAIR_DAYTONA_SMOKE_OK')\"", timeout=60)
    result = getattr(resp, "result", None) or str(resp)
    exit_code = getattr(resp, "exit_code", None)
    print("EXIT", exit_code)
    print("RESULT", result)
    if "REPAIR_DAYTONA_SMOKE_OK" in str(result):
        print("SMOKE_OK")
    else:
        print("SMOKE_BAD")
except Exception as e:
    print("ERROR_TYPE", type(e).__name__)
    print("ERROR", str(e))
    traceback.print_exc()
    raise
finally:
    if sandbox is not None:
        try:
            daytona.delete(sandbox)
            print("DELETED")
        except Exception as e:
            print("DELETE_ERROR", type(e).__name__, str(e))
"""
    proc = subprocess.run([str(DAYTONA_PYTHON), "-c", code], capture_output=True, text=True, env=_mask_env(), timeout=120)
    _write_artifact(ts_dir, "step2_stdout.txt", proc.stdout)
    _write_artifact(ts_dir, "step2_stderr.txt", proc.stderr)
    print(proc.stdout)
    if proc.stderr:
        print("stderr:", proc.stderr[-1200:])
    sid = None
    for ln in proc.stdout.splitlines():
        if ln.startswith("SANDBOX_ID "):
            sid = ln.split(" ", 1)[1].strip()
    ok = proc.returncode == 0 and "SMOKE_OK" in proc.stdout
    if ok:
        _ok("sandbox create/exec", f"sandbox_id={sid}")
    else:
        _fail("sandbox create/exec", f"rc={proc.returncode}")
    return {
        "step": 2,
        "ok": ok,
        "sandbox_id": sid,
        "stdout": proc.stdout[-3000:],
        "stderr": proc.stderr[-3000:],
        "returncode": proc.returncode,
    }


def step3(ts_dir: Path) -> dict:
    print("\n=== STEP 3 — file upload ===")
    code = r"""
import traceback
from daytona import Daytona, CreateSandboxFromSnapshotParams, FileUpload
sandbox = None
daytona = Daytona()
try:
    sandbox = daytona.create(CreateSandboxFromSnapshotParams(language="python"))
    sid = getattr(sandbox, "id", None) or getattr(sandbox, "instance_id", None)
    print("SANDBOX_ID", sid)
    content = b"REPAIR_UPLOAD_OK"
    sandbox.fs.upload_files([FileUpload(source=content, destination="repair_smoke.txt")])
    resp = sandbox.process.exec("cat repair_smoke.txt", timeout=60)
    result = getattr(resp, "result", None) or str(resp)
    print("RESULT", result)
    if "REPAIR_UPLOAD_OK" in str(result):
        print("UPLOAD_OK")
    else:
        print("UPLOAD_BAD")
except Exception as e:
    print("ERROR_TYPE", type(e).__name__)
    print("ERROR", str(e))
    traceback.print_exc()
    raise
finally:
    if sandbox is not None:
        try:
            daytona.delete(sandbox)
            print("DELETED")
        except Exception as e:
            print("DELETE_ERROR", type(e).__name__, str(e))
"""
    proc = subprocess.run([str(DAYTONA_PYTHON), "-c", code], capture_output=True, text=True, env=_mask_env(), timeout=120)
    _write_artifact(ts_dir, "step3_stdout.txt", proc.stdout)
    _write_artifact(ts_dir, "step3_stderr.txt", proc.stderr)
    print(proc.stdout)
    if proc.stderr:
        print("stderr:", proc.stderr[-1200:])
    sid = None
    for ln in proc.stdout.splitlines():
        if ln.startswith("SANDBOX_ID "):
            sid = ln.split(" ", 1)[1].strip()
    ok = proc.returncode == 0 and "UPLOAD_OK" in proc.stdout
    if ok:
        _ok("file upload", f"sandbox_id={sid}")
    else:
        _fail("file upload", f"rc={proc.returncode}")
    return {
        "step": 3,
        "ok": ok,
        "sandbox_id": sid,
        "stdout": proc.stdout[-3000:],
        "stderr": proc.stderr[-3000:],
        "returncode": proc.returncode,
    }


def step4(ts_dir: Path) -> dict:
    print("\n=== STEP 4 — real REPAIR harness in Daytona ===")
    if not all(p.exists() for p in (CANDIDATE, CASES, ENGINE_SRC, HARNESS_SRC, DAYTONA_SCRIPT)):
        _fail("harness inputs missing")
        return {"step": 4, "ok": False, "error": "missing inputs"}

    out = ts_dir / "step4_result.json"
    env = _mask_env()
    proc = subprocess.run(
        [
            str(DAYTONA_PYTHON),
            str(DAYTONA_SCRIPT),
            "--candidate",
            str(CANDIDATE),
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
    _write_artifact(ts_dir, "step4_stdout.txt", proc.stdout)
    _write_artifact(ts_dir, "step4_stderr.txt", proc.stderr)
    print("returncode", proc.returncode)
    print("stdout:", proc.stdout[-2000:])
    print("stderr:", proc.stderr[-2000:])
    result = None
    if out.exists():
        result = json.loads(out.read_text())
        print("result.json:", json.dumps(result, indent=2)[:2000])
    ok = (
        proc.returncode == 0
        and isinstance(result, dict)
        and result.get("executed_in") == "daytona"
        and bool(result.get("sandbox_id"))
    )
    if ok:
        _ok(
            "real harness",
            f"sandbox={result.get('sandbox_id')} verdict={result.get('verdict')}",
        )
    else:
        _fail("real harness", f"rc={proc.returncode} executed_in={result and result.get('executed_in')}")
    return {
        "step": 4,
        "ok": ok,
        "returncode": proc.returncode,
        "result": result,
        "stdout": proc.stdout[-3000:],
        "stderr": proc.stderr[-3000:],
        "candidate": str(CANDIDATE),
    }


def step5(ts_dir: Path) -> dict:
    print("\n=== STEP 5 — production evaluate_candidate_daytona ===")
    # Ensure engine src on path
    sys.path.insert(0, str(ENGINE_ROOT / "src"))
    from repair.evaluation.daytona_runner import evaluate_candidate_daytona

    policy = json.loads(CANDIDATE.read_text())
    run_id = f"diag-daytona-{ts_dir.name}"
    try:
        result = evaluate_candidate_daytona(policy, run_id=run_id)
    except Exception as e:
        tb = traceback.format_exc()
        _write_artifact(ts_dir, "step5_exception.txt", tb)
        _fail("evaluate_candidate_daytona", f"{type(e).__name__}: {e}")
        return {"step": 5, "ok": False, "error": str(e), "traceback": tb[-2000:]}

    _write_artifact(ts_dir, "step5_result.json", json.dumps(result, indent=2))
    print(json.dumps({k: result.get(k) for k in ("verdict", "executed_in", "sandbox_id", "reject_reasons")}, indent=2))
    if result.get("stdout"):
        print("stdout tail:", str(result.get("stdout"))[-800:])
    if result.get("stderr"):
        print("stderr tail:", str(result.get("stderr"))[-800:])
    ok = result.get("executed_in") == "daytona" and bool(result.get("sandbox_id"))
    if ok:
        _ok("evaluate_candidate_daytona", f"sandbox={result.get('sandbox_id')}")
    else:
        _fail("evaluate_candidate_daytona", f"executed_in={result.get('executed_in')}")
    return {"step": 5, "ok": ok, "result": result}


def step6(ts_dir: Path) -> dict:
    print("\n=== STEP 6 — Act 2 only (phases=learn) ===")
    print("NOTE: exercises CrewAI + You.com + Daytona; NO Stripe/Linear mutations.")
    sys.path.insert(0, str(ENGINE_ROOT / "src"))
    from repair.scenarios.demo import run_demo

    run_id = f"diag-learn-{ts_dir.name}"
    try:
        out = run_demo(run_id=run_id, phases=["learn"], skip_learning_if_promoted=False)
    except Exception as e:
        tb = traceback.format_exc()
        _write_artifact(ts_dir, "step6_exception.txt", tb)
        _fail("Act 2 learn", f"{type(e).__name__}: {e}")
        return {"step": 6, "ok": False, "error": str(e), "traceback": tb[-3000:]}

    _write_artifact(ts_dir, "step6_result.json", json.dumps(out, indent=2, default=str))
    learn = (out.get("phases") or {}).get("learn") or {}
    print(json.dumps({"ok": out.get("ok"), "learn": learn, "errors": out.get("errors")}, indent=2, default=str)[:3000])

    # Scan run events for evidence
    events_path = REPO_ROOT / "runs" / run_id / "events.jsonl"
    evidence = {
        "diagnosis_mode": None,
        "youcom": [],
        "daytona": [],
        "promoted": None,
    }
    if events_path.exists():
        for line in events_path.read_text().splitlines():
            e = json.loads(line)
            t = e.get("type")
            p = e.get("payload") or {}
            if t == "diagnosis.mode":
                evidence["diagnosis_mode"] = p
            if t == "research.evidence":
                caps = p.get("capabilities") or {}
                ev = caps.get("evidence") or {}
                evidence["youcom"].append(
                    {
                        "source": p.get("source") or caps.get("source"),
                        "search_uuid": p.get("search_uuid") or ev.get("search_uuid"),
                        "tool_id": p.get("tool_id"),
                    }
                )
            if t in ("candidate.rejected", "candidate.promoted", "evaluation.completed", "evaluation.failed"):
                evidence["daytona"].append({"type": t, "payload": p})
            if t == "candidate.promoted":
                evidence["promoted"] = p

    _write_artifact(ts_dir, "step6_evidence.json", json.dumps(evidence, indent=2))
    print("evidence:", json.dumps(evidence, indent=2)[:2500])

    ok = bool(out.get("ok")) and bool(learn.get("promoted"))
    # Also require at least one daytona executed_in if present in metrics
    daytona_live = False
    for item in evidence["daytona"]:
        p = item.get("payload") or {}
        metrics = p.get("metrics") or {}
        if metrics.get("executed_in") == "daytona" or p.get("mode") == "daytona" and p.get("sandbox_id"):
            daytona_live = True
        if p.get("sandbox_id") and item["type"] == "evaluation.completed":
            daytona_live = True
    if ok and daytona_live:
        _ok("Act 2 learn", f"promoted={learn.get('promoted_version')}")
    elif ok:
        _fail("Act 2 learn", "promoted but daytona live evidence unclear")
        ok = False
    else:
        _fail("Act 2 learn", str(out.get("errors") or learn)[:300])
    return {"step": 6, "ok": ok, "result": out, "evidence": evidence}


def main() -> int:
    _load_dotenv()
    # Clear proxies that break SDK from sandboxed/agent shells
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        os.environ.pop(k, None)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ts_dir = ARTIFACT_ROOT / ts
    ts_dir.mkdir(parents=True, exist_ok=True)
    print(f"artifact dir: {ts_dir}")

    summary: dict = {"timestamp": ts, "steps": {}}
    r0 = step0(ts_dir)
    summary["steps"]["0"] = r0
    if not r0.get("ok"):
        summary["failed_at"] = 0
        _write_artifact(ts_dir, "summary.json", json.dumps(summary, indent=2, default=str))
        return 1

    r1 = step1(ts_dir)
    summary["steps"]["1"] = r1
    if not r1.get("ok"):
        summary["failed_at"] = 1
        _write_artifact(ts_dir, "summary.json", json.dumps(summary, indent=2, default=str))
        return 1

    r2 = step2(ts_dir)
    summary["steps"]["2"] = r2
    if not r2.get("ok"):
        summary["failed_at"] = 2
        _write_artifact(ts_dir, "summary.json", json.dumps(summary, indent=2, default=str))
        return 1

    r3 = step3(ts_dir)
    summary["steps"]["3"] = r3
    if not r3.get("ok"):
        summary["failed_at"] = 3
        _write_artifact(ts_dir, "summary.json", json.dumps(summary, indent=2, default=str))
        return 1

    r4 = step4(ts_dir)
    summary["steps"]["4"] = r4
    if not r4.get("ok"):
        summary["failed_at"] = 4
        _write_artifact(ts_dir, "summary.json", json.dumps(summary, indent=2, default=str))
        return 1

    r5 = step5(ts_dir)
    summary["steps"]["5"] = r5
    if not r5.get("ok"):
        summary["failed_at"] = 5
        _write_artifact(ts_dir, "summary.json", json.dumps(summary, indent=2, default=str))
        return 1

    # Only if 1-5 pass
    r6 = step6(ts_dir)
    summary["steps"]["6"] = r6
    summary["failed_at"] = None if r6.get("ok") else 6
    summary["overall_ok"] = bool(r6.get("ok"))
    _write_artifact(ts_dir, "summary.json", json.dumps(summary, indent=2, default=str))
    print("\n=== SUMMARY ===")
    print(json.dumps({"overall_ok": summary["overall_ok"], "failed_at": summary["failed_at"], "artifact": str(ts_dir)}, indent=2))
    return 0 if summary["overall_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
