#!/usr/bin/env python3
"""Reset demo state for a clean rehearsal (does not wipe promoted policies)."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from repair.config import REPO_ROOT, get_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset REPAIR demo run artifacts")
    parser.add_argument("--keep-golden", action="store_true", help="Preserve runs/golden/")
    parser.add_argument("--archive-runs", action="store_true", help="Move runs/* to runs/_archive/")
    args = parser.parse_args()

    settings = get_settings()
    runs = settings.runs_dir
    runs.mkdir(parents=True, exist_ok=True)

    if args.archive_runs:
        archive = runs / "_archive" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive.mkdir(parents=True, exist_ok=True)
        for child in runs.iterdir():
            if child.name in {"_archive", "golden"} and args.keep_golden:
                continue
            if child.name == "_archive":
                continue
            if child.name == "golden" and args.keep_golden:
                continue
            dest = archive / child.name
            shutil.move(str(child), str(dest))
        print(f"archived runs -> {archive}")
    else:
        removed = 0
        for child in runs.iterdir():
            if child.name in {"_archive", "golden"}:
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
            removed += 1
        print(f"cleared {removed} run artifacts under {runs}")

    # Ensure V3 remains active if promoted file exists
    promoted = settings.policies_dir / "promoted" / "v3.json"
    registry_path = settings.policies_dir / "registry.json"
    if promoted.exists():
        from repair.models import LearnedPolicy
        from repair.runtime.registry import PolicyRegistry

        reg = PolicyRegistry(registry_path)
        policy = LearnedPolicy.model_validate(json.loads(promoted.read_text()))
        if not any(p.version == 3 for p in reg.active):
            reg.promote(policy)
            print("restored V3 into registry.active")
        else:
            print("registry already has V3 active")

    preflight = REPO_ROOT / "fixtures" / "preflight" / "stripe_test_mode.json"
    if preflight.exists():
        marker = json.loads(preflight.read_text())
        print("stripe preflight:", marker.get("result"), "livemode=", marker.get("livemode"))
    else:
        print("WARNING: stripe_test_mode.json missing — re-run preflight before Stripe mutations")

    print("reset complete")


if __name__ == "__main__":
    main()
