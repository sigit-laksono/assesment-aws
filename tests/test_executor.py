"""
Tests for BoundedExecutor and Aggregate Status Views.

Covers:
- Global concurrency bound is respected
- Per-account concurrency bound is respected
- Prerequisite ordering (unit waits for prereqs)
- Failed prerequisite causes dependent unit to fail
- aggregate_run_status for all combinations (all succeed, mixed, all fail)
- aggregate_account_status and region_status
- Exception at boundary is translated to failed UnitResult
- CollectorOutcome.status == "failed" produces failed unit
- Uses threading primitives (barriers, events) to verify concurrency limits
- No real AWS calls
"""

from __future__ import annotations

import threading
import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from agentic.executor import (
    BoundedExecutor,
    UnitExecutionState,
    aggregate_account_status,
    aggregate_capability_status,
    aggregate_region_status,
    aggregate_run_status,
)
from agentic.models import (
    AccountTarget,
    CollectorOutcome,
    ExecutionPlan,
    ExecutionUnit,
    StructuredError,
    UnitResult,
)


# ---------------------------------------------------------------------------
# Test Fixtures and Helpers
# ---------------------------------------------------------------------------


def _make_unit(
    unit_id: str,
    ordinal: int = 0,
    capability_id: str = "ec2.inventory",
    account_id: str = "111111111111",
    region_scope: str = "us-east-1",
    prerequisite_unit_ids: tuple[str, ...] = (),
) -> ExecutionUnit:
    """Helper to create an ExecutionUnit with sensible defaults."""
    return ExecutionUnit(
        unit_id=unit_id,
        ordinal=ordinal,
        capability_id=capability_id,
        capability_version="1.0.0",
        account_id=account_id,
        region_scope=region_scope,
        parameters={},
        prerequisite_unit_ids=prerequisite_unit_ids,
    )


def _make_plan(units: list[ExecutionUnit]) -> ExecutionPlan:
    """Helper to create an ExecutionPlan from a list of units."""
    return ExecutionPlan(
        request_digest="test-digest",
        manifest_digest="test-manifest",
        units=tuple(units),
        plan_digest="test-plan-digest",
    )


def _success_collector(unit: ExecutionUnit, session: Any) -> CollectorOutcome:
    """Collector that always succeeds."""
    return CollectorOutcome(status="succeeded", records=(), evidence=(), attempts=1)


def _failure_collector(unit: ExecutionUnit, session: Any) -> CollectorOutcome:
    """Collector that always returns failed status."""
    return CollectorOutcome(
        status="failed",
        records=(),
        evidence=(),
        error=StructuredError(
            code="COLLECTOR_ERROR",
            category="internal",
            retryable=False,
            safe_message="Simulated failure",
        ),
        attempts=1,
    )


def _exception_collector(unit: ExecutionUnit, session: Any) -> CollectorOutcome:
    """Collector that always raises an exception."""
    raise RuntimeError("Unexpected collector crash")


class FakeSessionFactory:
    """Fake SessionFactory for testing — returns a MagicMock session."""

    def for_account(self, target: AccountTarget) -> Any:
        return MagicMock()


# ---------------------------------------------------------------------------
# BoundedExecutor Tests
# ---------------------------------------------------------------------------


class TestBoundedExecutorBasic:
    """Basic execution tests."""

    def test_empty_plan_returns_empty_tuple(self):
        executor = BoundedExecutor()
        plan = _make_plan([])
        results = executor.execute(plan, _success_collector, FakeSessionFactory())
        assert results == ()

    def test_single_unit_succeeds(self):
        unit = _make_unit("u1", ordinal=0)
        plan = _make_plan([unit])
        executor = BoundedExecutor()
        results = executor.execute(plan, _success_collector, FakeSessionFactory())
        assert len(results) == 1
        assert results[0].unit_id == "u1"
        assert results[0].status == "succeeded"

    def test_multiple_units_all_succeed(self):
        units = [_make_unit(f"u{i}", ordinal=i) for i in range(5)]
        plan = _make_plan(units)
        executor = BoundedExecutor()
        results = executor.execute(plan, _success_collector, FakeSessionFactory())
        assert len(results) == 5
        assert all(r.status == "succeeded" for r in results)

    def test_results_ordered_by_ordinal(self):
        units = [
            _make_unit("u2", ordinal=2),
            _make_unit("u0", ordinal=0),
            _make_unit("u1", ordinal=1),
        ]
        plan = _make_plan(units)
        executor = BoundedExecutor()
        results = executor.execute(plan, _success_collector, FakeSessionFactory())
        assert [r.unit_id for r in results] == ["u0", "u1", "u2"]


class TestBoundedExecutorConcurrency:
    """Tests for concurrency bounds using threading primitives."""

    def test_global_concurrency_bound_respected(self):
        """Verify at most global_concurrency units run concurrently."""
        global_limit = 2
        max_concurrent = {"value": 0}
        current_concurrent = {"value": 0}
        lock = threading.Lock()

        def tracking_collector(unit: ExecutionUnit, session: Any) -> CollectorOutcome:
            with lock:
                current_concurrent["value"] += 1
                if current_concurrent["value"] > max_concurrent["value"]:
                    max_concurrent["value"] = current_concurrent["value"]
            time.sleep(0.05)  # Simulate I/O
            with lock:
                current_concurrent["value"] -= 1
            return CollectorOutcome(status="succeeded", records=(), evidence=(), attempts=1)

        units = [_make_unit(f"u{i}", ordinal=i) for i in range(6)]
        plan = _make_plan(units)
        executor = BoundedExecutor(global_concurrency=global_limit, per_account_concurrency=10)
        executor.execute(plan, tracking_collector, FakeSessionFactory())

        assert max_concurrent["value"] <= global_limit

    def test_per_account_concurrency_bound_respected(self):
        """Verify at most per_account_concurrency units run per account."""
        per_account_limit = 2
        max_concurrent_per_account: dict[str, int] = {}
        current_per_account: dict[str, int] = {}
        lock = threading.Lock()

        def tracking_collector(unit: ExecutionUnit, session: Any) -> CollectorOutcome:
            acct = unit.account_id
            with lock:
                current_per_account[acct] = current_per_account.get(acct, 0) + 1
                if current_per_account[acct] > max_concurrent_per_account.get(acct, 0):
                    max_concurrent_per_account[acct] = current_per_account[acct]
            time.sleep(0.05)
            with lock:
                current_per_account[acct] -= 1
            return CollectorOutcome(status="succeeded", records=(), evidence=(), attempts=1)

        # 6 units across 2 accounts (3 each)
        units = [
            _make_unit("a1-u0", ordinal=0, account_id="acct-1"),
            _make_unit("a1-u1", ordinal=1, account_id="acct-1"),
            _make_unit("a1-u2", ordinal=2, account_id="acct-1"),
            _make_unit("a2-u0", ordinal=3, account_id="acct-2"),
            _make_unit("a2-u1", ordinal=4, account_id="acct-2"),
            _make_unit("a2-u2", ordinal=5, account_id="acct-2"),
        ]
        plan = _make_plan(units)
        executor = BoundedExecutor(global_concurrency=10, per_account_concurrency=per_account_limit)
        executor.execute(plan, tracking_collector, FakeSessionFactory())

        for acct, max_val in max_concurrent_per_account.items():
            assert max_val <= per_account_limit, (
                f"Account {acct} exceeded limit: {max_val} > {per_account_limit}"
            )


class TestBoundedExecutorPrerequisites:
    """Tests for prerequisite ordering."""

    def test_unit_waits_for_prerequisites(self):
        """A unit with prerequisite_unit_ids only runs after prereqs complete."""
        execution_order: list[str] = []
        lock = threading.Lock()

        def ordered_collector(unit: ExecutionUnit, session: Any) -> CollectorOutcome:
            # First unit takes some time
            if unit.unit_id == "u0":
                time.sleep(0.1)
            with lock:
                execution_order.append(unit.unit_id)
            return CollectorOutcome(status="succeeded", records=(), evidence=(), attempts=1)

        units = [
            _make_unit("u0", ordinal=0),
            _make_unit("u1", ordinal=1, prerequisite_unit_ids=("u0",)),
        ]
        plan = _make_plan(units)
        executor = BoundedExecutor(global_concurrency=4)
        results = executor.execute(plan, ordered_collector, FakeSessionFactory())

        assert execution_order.index("u0") < execution_order.index("u1")
        assert all(r.status == "succeeded" for r in results)

    def test_failed_prerequisite_causes_dependent_to_fail(self):
        """If a prerequisite fails, dependent units also fail."""
        units = [
            _make_unit("u0", ordinal=0),
            _make_unit("u1", ordinal=1, prerequisite_unit_ids=("u0",)),
            _make_unit("u2", ordinal=2, prerequisite_unit_ids=("u1",)),
        ]
        plan = _make_plan(units)
        executor = BoundedExecutor()
        results = executor.execute(plan, _failure_collector, FakeSessionFactory())

        assert results[0].status == "failed"
        assert results[1].status == "failed"
        assert results[1].error is not None
        assert results[1].error.code == "PREREQUISITE_FAILED"
        assert results[2].status == "failed"
        assert results[2].error is not None
        assert results[2].error.code == "PREREQUISITE_FAILED"

    def test_independent_units_not_blocked_by_failed_sibling(self):
        """Units without prereqs on a failed unit still run independently."""
        def selective_collector(unit: ExecutionUnit, session: Any) -> CollectorOutcome:
            if unit.unit_id == "u0":
                return CollectorOutcome(
                    status="failed",
                    records=(),
                    evidence=(),
                    error=StructuredError(
                        code="FAIL", category="internal", retryable=False,
                        safe_message="fail",
                    ),
                    attempts=1,
                )
            return CollectorOutcome(status="succeeded", records=(), evidence=(), attempts=1)

        units = [
            _make_unit("u0", ordinal=0),
            _make_unit("u1", ordinal=1, prerequisite_unit_ids=("u0",)),
            _make_unit("u2", ordinal=2),  # No prereqs — should run fine
        ]
        plan = _make_plan(units)
        executor = BoundedExecutor()
        results = executor.execute(plan, selective_collector, FakeSessionFactory())

        result_map = {r.unit_id: r for r in results}
        assert result_map["u0"].status == "failed"
        assert result_map["u1"].status == "failed"
        assert result_map["u1"].error.code == "PREREQUISITE_FAILED"
        assert result_map["u2"].status == "succeeded"


class TestBoundedExecutorErrorHandling:
    """Tests for error handling at executor boundary."""

    def test_exception_translated_to_failed_unit_result(self):
        """Exceptions raised in collector are caught and translated."""
        unit = _make_unit("u1", ordinal=0)
        plan = _make_plan([unit])
        executor = BoundedExecutor()
        results = executor.execute(plan, _exception_collector, FakeSessionFactory())

        assert len(results) == 1
        assert results[0].status == "failed"
        assert results[0].error is not None
        assert results[0].error.code == "EXECUTOR_EXCEPTION"
        assert "Unexpected collector crash" in results[0].error.safe_message

    def test_collector_outcome_failed_produces_failed_unit(self):
        """CollectorOutcome.status == 'failed' produces a failed UnitResult."""
        unit = _make_unit("u1", ordinal=0)
        plan = _make_plan([unit])
        executor = BoundedExecutor()
        results = executor.execute(plan, _failure_collector, FakeSessionFactory())

        assert len(results) == 1
        assert results[0].status == "failed"
        assert results[0].error is not None
        assert results[0].error.code == "COLLECTOR_ERROR"


# ---------------------------------------------------------------------------
# Aggregate Status Tests
# ---------------------------------------------------------------------------


class TestAggregateRunStatus:
    """Tests for aggregate_run_status."""

    def test_all_succeeded(self):
        results = (
            UnitResult(unit_id="u1", status="succeeded"),
            UnitResult(unit_id="u2", status="succeeded"),
            UnitResult(unit_id="u3", status="succeeded"),
        )
        assert aggregate_run_status(results) == "succeeded"

    def test_all_failed(self):
        results = (
            UnitResult(unit_id="u1", status="failed"),
            UnitResult(unit_id="u2", status="failed"),
        )
        assert aggregate_run_status(results) == "failed"

    def test_mixed_partial_success(self):
        results = (
            UnitResult(unit_id="u1", status="succeeded"),
            UnitResult(unit_id="u2", status="failed"),
        )
        assert aggregate_run_status(results) == "partial-success"

    def test_cancelled_overrides(self):
        results = (
            UnitResult(unit_id="u1", status="succeeded"),
            UnitResult(unit_id="u2", status="succeeded"),
        )
        assert aggregate_run_status(results, cancelled=True) == "cancelled"

    def test_empty_results(self):
        assert aggregate_run_status(()) == "succeeded"

    def test_single_success(self):
        results = (UnitResult(unit_id="u1", status="succeeded"),)
        assert aggregate_run_status(results) == "succeeded"

    def test_single_failure(self):
        results = (UnitResult(unit_id="u1", status="failed"),)
        assert aggregate_run_status(results) == "failed"

    def test_order_independence(self):
        """Status derivation does not depend on result order."""
        results_a = (
            UnitResult(unit_id="u1", status="succeeded"),
            UnitResult(unit_id="u2", status="failed"),
            UnitResult(unit_id="u3", status="succeeded"),
        )
        results_b = (
            UnitResult(unit_id="u2", status="failed"),
            UnitResult(unit_id="u3", status="succeeded"),
            UnitResult(unit_id="u1", status="succeeded"),
        )
        assert aggregate_run_status(results_a) == aggregate_run_status(results_b)
        assert aggregate_run_status(results_a) == "partial-success"


class TestAggregateAccountStatus:
    """Tests for aggregate_account_status."""

    def test_filters_by_account(self):
        results = (
            UnitResult(unit_id="u1", account_id="acct-1", status="succeeded"),
            UnitResult(unit_id="u2", account_id="acct-1", status="failed"),
            UnitResult(unit_id="u3", account_id="acct-2", status="succeeded"),
        )
        assert aggregate_account_status(results, "acct-1") == "partial-success"
        assert aggregate_account_status(results, "acct-2") == "succeeded"

    def test_nonexistent_account(self):
        results = (UnitResult(unit_id="u1", account_id="acct-1", status="succeeded"),)
        assert aggregate_account_status(results, "nonexistent") == "succeeded"


class TestAggregateRegionStatus:
    """Tests for aggregate_region_status."""

    def test_filters_by_region(self):
        results = (
            UnitResult(unit_id="u1", region_scope="us-east-1", status="succeeded"),
            UnitResult(unit_id="u2", region_scope="us-east-1", status="failed"),
            UnitResult(unit_id="u3", region_scope="eu-west-1", status="succeeded"),
        )
        assert aggregate_region_status(results, "us-east-1") == "partial-success"
        assert aggregate_region_status(results, "eu-west-1") == "succeeded"


class TestAggregateCapabilityStatus:
    """Tests for aggregate_capability_status."""

    def test_filters_by_capability(self):
        results = (
            UnitResult(unit_id="u1", capability_id="ec2.inventory", status="succeeded"),
            UnitResult(unit_id="u2", capability_id="ec2.inventory", status="failed"),
            UnitResult(unit_id="u3", capability_id="s3.inventory", status="succeeded"),
        )
        assert aggregate_capability_status(results, "ec2.inventory") == "partial-success"
        assert aggregate_capability_status(results, "s3.inventory") == "succeeded"

    def test_all_failed_for_capability(self):
        results = (
            UnitResult(unit_id="u1", capability_id="ec2.inventory", status="failed"),
            UnitResult(unit_id="u2", capability_id="ec2.inventory", status="failed"),
            UnitResult(unit_id="u3", capability_id="s3.inventory", status="succeeded"),
        )
        assert aggregate_capability_status(results, "ec2.inventory") == "failed"
