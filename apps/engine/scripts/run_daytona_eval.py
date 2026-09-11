#!/usr/bin/env python3
"""Run REPAIR harness inside a real Daytona sandbox. Invoked from isolated daytona venv."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--engine", required=True)
    parser.add_argument("--harness", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    if not os.environ.get("DAYTONA_API_KEY"):
        print(json.dumps({"verdict": "REJECT", "reject_reasons": ["DAYTONA_API_KEY missing"], "executed_in": "daytona_failed"}))
        return 2

    from daytona import Daytona, CreateSandboxFromSnapshotParams, FileUpload  # type: ignore

    candidate = Path(args.candidate).read_bytes()
    cases = Path(args.cases).read_bytes()
    engine = Path(args.engine).read_bytes()
    harness = Path(args.harness).read_bytes()

    daytona = Daytona()
    sandbox = daytona.create(CreateSandboxFromSnapshotParams(language="python"))
    sandbox_id = getattr(sandbox, "id", None) or getattr(sandbox, "instance_id", None)
    try:
        sandbox.fs.upload_files(
            [
                FileUpload(source=engine, destination="policy_engine.py"),
                FileUpload(source=harness, destination="harness.py"),
                FileUpload(source=candidate, destination="candidate.json"),
                FileUpload(source=cases, destination="eval_cases.json"),
            ]
        )
        resp = sandbox.process.exec(
            "python3 harness.py --candidate candidate.json --cases eval_cases.json",
            timeout=90,
        )
        raw = (getattr(resp, "result", None) or str(resp) or "").strip()
        lines = [ln for ln in raw.splitlines() if ln.strip()]
        payload = json.loads(lines[-1]) if lines else {"verdict": "REJECT", "reject_reasons": ["empty_stdout"]}
        payload["sandbox_id"] = sandbox_id
        payload["executed_in"] = "daytona"
        payload["exit_code"] = getattr(resp, "exit_code", None)
        Path(args.out).write_text(json.dumps(payload, indent=2))
        print(json.dumps(payload))
        return 0
    except Exception as exc:
        err = {
            "verdict": "REJECT",
            "reject_reasons": ["daytona_exec_error"],
            "daytona_error": str(exc),
            "sandbox_id": sandbox_id,
            "executed_in": "daytona_failed",
        }
        Path(args.out).write_text(json.dumps(err, indent=2))
        print(json.dumps(err))
        return 1
    finally:
        try:
            daytona.delete(sandbox)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
