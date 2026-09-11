#!/usr/bin/env python3
"""Run REPAIR harness inside a real Daytona sandbox. Invoked from isolated daytona venv."""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--engine", required=True)
    parser.add_argument("--harness", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    out_path = Path(args.out)

    def write_err(payload: dict, code: int = 1) -> int:
        payload.setdefault("verdict", "REJECT")
        payload.setdefault("executed_in", "daytona_failed")
        out_path.write_text(json.dumps(payload, indent=2))
        print(json.dumps(payload))
        return code

    if not os.environ.get("DAYTONA_API_KEY"):
        return write_err({"reject_reasons": ["DAYTONA_API_KEY missing"]}, 2)

    try:
        from daytona import Daytona, CreateSandboxFromSnapshotParams, FileUpload  # type: ignore
    except Exception as exc:
        return write_err(
            {
                "reject_reasons": ["daytona_import_error"],
                "daytona_error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc()[-2000:],
            }
        )

    try:
        candidate = Path(args.candidate).read_bytes()
        cases = Path(args.cases).read_bytes()
        engine = Path(args.engine).read_bytes()
        harness = Path(args.harness).read_bytes()
    except Exception as exc:
        return write_err(
            {
                "reject_reasons": ["daytona_input_read_error"],
                "daytona_error": f"{type(exc).__name__}: {exc}",
            }
        )

    daytona = None
    sandbox = None
    sandbox_id = None
    try:
        daytona = Daytona()
        sandbox = daytona.create(CreateSandboxFromSnapshotParams(language="python"))
        sandbox_id = getattr(sandbox, "id", None) or getattr(sandbox, "instance_id", None)
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
        if not lines:
            return write_err(
                {
                    "reject_reasons": ["empty_stdout"],
                    "sandbox_id": sandbox_id,
                    "exit_code": getattr(resp, "exit_code", None),
                    "raw_result": raw[-1500:],
                }
            )
        try:
            payload = json.loads(lines[-1])
        except json.JSONDecodeError as exc:
            return write_err(
                {
                    "reject_reasons": ["harness_parse_error"],
                    "daytona_error": str(exc),
                    "sandbox_id": sandbox_id,
                    "raw_result": raw[-1500:],
                    "exit_code": getattr(resp, "exit_code", None),
                }
            )
        payload["sandbox_id"] = sandbox_id
        payload["executed_in"] = "daytona"
        payload["exit_code"] = getattr(resp, "exit_code", None)
        out_path.write_text(json.dumps(payload, indent=2))
        print(json.dumps(payload))
        return 0
    except Exception as exc:
        return write_err(
            {
                "reject_reasons": ["daytona_exec_error"],
                "daytona_error": f"{type(exc).__name__}: {exc}",
                "sandbox_id": sandbox_id,
                "traceback": traceback.format_exc()[-2000:],
            }
        )
    finally:
        if daytona is not None and sandbox is not None:
            try:
                daytona.delete(sandbox)
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
