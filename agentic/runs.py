"""
Agentic AWS Assessment — Persisted Run Listing (Requirement 11.2).

One pure function that scans `output/agentic/runs/` for the timestamped
per-run JSON files written on terminal status (Requirement 11.1) and
returns them, optionally filtered by `account_id`. No index file, no
retention policy, no digest — just a directory scan.
"""

from __future__ import annotations

import json
from pathlib import Path

RUNS_DIR = Path("output") / "agentic" / "runs"


def _matches_account_id(data: object, account_id: str) -> bool:
    """Recursively check whether any `account_id` field equals the target.

    InvocationResult has no top-level `account_id`; it lives on nested
    `unit_results[*].account_id` / `capability_summaries[*].account_id`.
    A generic walk avoids hard-coding that shape here.
    """
    if isinstance(data, dict):
        if data.get("account_id") == account_id:
            return True
        return any(_matches_account_id(value, account_id) for value in data.values())
    if isinstance(data, list):
        return any(_matches_account_id(item, account_id) for item in data)
    return False


def list_runs(account_id: str | None = None) -> list[Path]:
    """
    List persisted run JSON files under `output/agentic/runs/`.

    Returns an empty list if the directory does not exist (it is not
    auto-created). When `account_id` is given, only files whose name
    contains it or whose JSON content has a matching `account_id` field
    are returned. Files that fail to read/parse are skipped silently.
    Result is sorted by filename (timestamp-based), so order is
    deterministic.
    """
    if not RUNS_DIR.is_dir():
        return []

    paths = sorted(RUNS_DIR.glob("*.json"))
    if account_id is None:
        return paths

    matched: list[Path] = []
    for path in paths:
        if account_id in path.name:
            matched.append(path)
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if _matches_account_id(data, account_id):
            matched.append(path)
    return matched


if __name__ == "__main__":
    # ponytail: minimal runnable self-check; full coverage lands in Task 7.3.
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        original_runs_dir = RUNS_DIR
        globals()["RUNS_DIR"] = Path(tmp)

        assert list_runs() == []

        run_a = Path(tmp) / "20240101T000000Z.json"
        run_a.write_text(
            json.dumps({"unit_results": [{"account_id": "111111111111"}]}),
            encoding="utf-8",
        )
        run_b = Path(tmp) / "20240102T000000Z.json"
        run_b.write_text(
            json.dumps({"unit_results": [{"account_id": "222222222222"}]}),
            encoding="utf-8",
        )
        bad = Path(tmp) / "20240103T000000Z.json"
        bad.write_text("not valid json", encoding="utf-8")

        assert list_runs() == [run_a, run_b, bad]
        assert list_runs(account_id="111111111111") == [run_a]
        assert list_runs(account_id="999999999999") == []

        globals()["RUNS_DIR"] = original_runs_dir

    print("list_runs() self-check passed")
