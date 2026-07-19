"""
Tests for agentic.runs.list_runs (Requirement 11.1, 11.2).

Covers:
- Returns [] when the runs directory does not exist.
- Returns all run files sorted when no account_id filter is given.
- Filters by account_id via filename substring match.
- Filters by account_id via JSON content match (nested field).
- Silently skips a run file with invalid JSON when filtering by account_id.

All tests use monkeypatch to point `agentic.runs.RUNS_DIR` at a tmp_path
directory — the real `output/agentic/runs/` directory is never touched.
"""

from __future__ import annotations

import json
from pathlib import Path

from agentic import runs


class TestListRunsMissingDirectory:
    def test_returns_empty_list_when_directory_missing(self, tmp_path, monkeypatch):
        missing_dir = tmp_path / "does-not-exist"
        monkeypatch.setattr(runs, "RUNS_DIR", missing_dir)

        assert runs.list_runs() == []


class TestListRunsNoFilter:
    def test_returns_all_run_files_sorted(self, tmp_path, monkeypatch):
        monkeypatch.setattr(runs, "RUNS_DIR", tmp_path)

        run_b = tmp_path / "20240102T000000Z.json"
        run_a = tmp_path / "20240101T000000Z.json"
        run_b.write_text(json.dumps({"unit_results": []}), encoding="utf-8")
        run_a.write_text(json.dumps({"unit_results": []}), encoding="utf-8")

        result = runs.list_runs()

        assert result == sorted([run_a, run_b])


class TestListRunsAccountIdFilter:
    def test_filters_by_filename_match(self, tmp_path, monkeypatch):
        monkeypatch.setattr(runs, "RUNS_DIR", tmp_path)

        run_with_id_in_name = tmp_path / "20240101T000000Z-111111111111.json"
        run_with_id_in_name.write_text(
            json.dumps({"unit_results": []}), encoding="utf-8"
        )
        run_other = tmp_path / "20240102T000000Z.json"
        run_other.write_text(
            json.dumps({"unit_results": [{"account_id": "222222222222"}]}),
            encoding="utf-8",
        )

        result = runs.list_runs(account_id="111111111111")

        assert result == [run_with_id_in_name]

    def test_filters_by_json_content_match(self, tmp_path, monkeypatch):
        monkeypatch.setattr(runs, "RUNS_DIR", tmp_path)

        run_a = tmp_path / "20240101T000000Z.json"
        run_a.write_text(
            json.dumps({"unit_results": [{"account_id": "111111111111"}]}),
            encoding="utf-8",
        )
        run_b = tmp_path / "20240102T000000Z.json"
        run_b.write_text(
            json.dumps(
                {"capability_summaries": [{"account_id": "222222222222"}]}
            ),
            encoding="utf-8",
        )

        result = runs.list_runs(account_id="111111111111")

        assert result == [run_a]

    def test_no_match_returns_empty_list(self, tmp_path, monkeypatch):
        monkeypatch.setattr(runs, "RUNS_DIR", tmp_path)

        run_a = tmp_path / "20240101T000000Z.json"
        run_a.write_text(
            json.dumps({"unit_results": [{"account_id": "111111111111"}]}),
            encoding="utf-8",
        )

        assert runs.list_runs(account_id="999999999999") == []


class TestListRunsInvalidJson:
    def test_invalid_json_skipped_silently_when_filtering(self, tmp_path, monkeypatch):
        monkeypatch.setattr(runs, "RUNS_DIR", tmp_path)

        good_run = tmp_path / "20240101T000000Z.json"
        good_run.write_text(
            json.dumps({"unit_results": [{"account_id": "111111111111"}]}),
            encoding="utf-8",
        )
        bad_run = tmp_path / "20240102T000000Z.json"
        bad_run.write_text("not valid json", encoding="utf-8")

        result = runs.list_runs(account_id="111111111111")

        assert result == [good_run]

    def test_invalid_json_included_in_unfiltered_listing(self, tmp_path, monkeypatch):
        """No filter means no parsing is attempted, so bad JSON still lists."""
        monkeypatch.setattr(runs, "RUNS_DIR", tmp_path)

        good_run = tmp_path / "20240101T000000Z.json"
        good_run.write_text(json.dumps({"unit_results": []}), encoding="utf-8")
        bad_run = tmp_path / "20240102T000000Z.json"
        bad_run.write_text("not valid json", encoding="utf-8")

        assert runs.list_runs() == sorted([good_run, bad_run])
