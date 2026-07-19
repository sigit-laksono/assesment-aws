# Feature: agentic-aws-assessment, Property 9: Execution respects the concurrency bound
# Validates: Requirements 6.6
"""
Property-based test for BoundedExecutor concurrency bound enforcement.

This test validates that for ALL finite execution plans and ALL positive
configured concurrency limits (global and per-account), the executor never
runs more execution units concurrently than the declared limit at any point
in time (Req 6.6): additional ready units are queued rather than dispatched
once a bound is reached.

An instrumented collector (spy) tracks, under a lock, how many units are
concurrently "in flight" both globally and per account, recording the
running maximum observed. The test asserts that maximum never exceeds the
Hypothesis-generated positive limit.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import hypothesis.strategies as st
from hypothesis import HealthCheck, given, settings

from agentic.executor import BoundedExecutor
from agentic.models import (
    AccountTarget,
    CollectorOutcome,
    ExecutionPlan,
    ExecutionUnit,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeSessionFactory:
    """Fake SessionFactory for testing — returns a plain object session."""

    def for_account(self, target: AccountTarget) -> Any:
        return object()


def _make_unit(unit_id: str, ordinal: int, account_id: str) -> ExecutionUnit:
    """Helper to create a prerequisite-free ExecutionUnit."""
    return ExecutionUnit(
        unit_id=unit_id,
        ordinal=ordinal,
        capability_id="ec2.inventory",
        capability_version="1.0.0",
        account_id=account_id,
        region_scope="us-east-1",
        parameters={},
        prerequisite_unit_ids=(),
    )


def _make_plan(units: list[ExecutionUnit]) -> ExecutionPlan:
    """Helper to create an ExecutionPlan from a list of units."""
    return ExecutionPlan(
        request_digest="test-digest",
        manifest_digest="test-manifest",
        units=tuple(units),
        plan_digest="test-plan-digest",
    )


# ---------------------------------------------------------------------------
# Hypothesis strategy: finite plans + positive concurrency limits
# ---------------------------------------------------------------------------

_ACCOUNT_POOL = ["111111111111", "222222222222", "333333333333"]


@st.composite
def finite_plan_and_limits(draw: st.DrawFn):
    """
    Generate a finite, prerequisite-free execution plan spread across a
    small set of accounts, plus positive global and per-account
    concurrency limits.

    Returns (plan, global_limit, per_account_limit).
    """
    num_accounts = draw(st.integers(min_value=1, max_value=3))
    accounts = _ACCOUNT_POOL[:num_accounts]

    num_units = draw(st.integers(min_value=1, max_value=9))
    account_choices = draw(
        st.lists(
            st.sampled_from(accounts),
            min_size=num_units,
            max_size=num_units,
        )
    )

    units = [
        _make_unit(f"u{i}", ordinal=i, account_id=account_choices[i])
        for i in range(num_units)
    ]
    plan = _make_plan(units)

    global_limit = draw(st.integers(min_value=1, max_value=5))
    per_account_limit = draw(st.integers(min_value=1, max_value=5))

    return (plan, global_limit, per_account_limit)


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@given(data=finite_plan_and_limits())
def test_execution_respects_the_concurrency_bound(data: tuple) -> None:
    """
    Property 9: Execution respects the concurrency bound.

    **Validates: Requirements 6.6**

    For any finite execution plan and any positive global/per-account
    concurrency limit, at no point during execution does the number of
    concurrently running execution units exceed the configured global
    bound, nor does the number of concurrently running units for any
    single account exceed the configured per-account bound.
    """
    plan, global_limit, per_account_limit = data

    global_active = {"value": 0}
    global_max = {"value": 0}
    per_account_active: dict[str, int] = {}
    per_account_max: dict[str, int] = {}
    lock = threading.Lock()

    def instrumented_collector(unit: ExecutionUnit, session: Any) -> CollectorOutcome:
        acct = unit.account_id
        with lock:
            global_active["value"] += 1
            if global_active["value"] > global_max["value"]:
                global_max["value"] = global_active["value"]

            per_account_active[acct] = per_account_active.get(acct, 0) + 1
            if per_account_active[acct] > per_account_max.get(acct, 0):
                per_account_max[acct] = per_account_active[acct]

        # Yield to other threads so genuine overlap has a chance to occur.
        time.sleep(0.01)

        with lock:
            global_active["value"] -= 1
            per_account_active[acct] -= 1

        return CollectorOutcome(status="succeeded", records=(), evidence=(), attempts=1)

    executor = BoundedExecutor(
        global_concurrency=global_limit,
        per_account_concurrency=per_account_limit,
    )
    results = executor.execute(plan, instrumented_collector, FakeSessionFactory())

    # Sanity: every unit reached a terminal state.
    assert len(results) == len(plan.units)
    assert all(r.status == "succeeded" for r in results)

    # The observed peak concurrency must never exceed the declared bounds.
    assert global_max["value"] <= global_limit, (
        f"Global concurrency bound violated: observed {global_max['value']} "
        f"concurrently running units, but limit was {global_limit}."
    )
    for acct, observed_max in per_account_max.items():
        assert observed_max <= per_account_limit, (
            f"Per-account concurrency bound violated for account {acct}: "
            f"observed {observed_max} concurrently running units, but limit "
            f"was {per_account_limit}."
        )
