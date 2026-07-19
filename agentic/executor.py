"""
Agentic AWS Assessment — Bounded Executor and Aggregate Status Views.

Implements:
- BoundedExecutor: Runs ready execution units with configurable global and
  per-account concurrency bounds. Respects prerequisite ordering. Queues
  units whose prerequisites are not yet complete. Catches exceptions at the
  executor boundary and translates them to failed UnitResult with StructuredError.
  (Req 6.4, 6.5, 6.6)
- Aggregate status derivation: Derives run, account, region, and capability
  statuses from immutable unit results without depending on completion order.
  (Req 9.1, 9.3)

Concurrency default: 4 global, 4 per-account. boto3 calls are I/O-bound so
threads are appropriate. Terminal aggregate output cannot contain queued,
running, or retry_wait units.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum
from typing import Any, Callable

from agentic.interfaces import GuardedSession, SessionFactory
from agentic.models import (
    AccountTarget,
    CollectorOutcome,
    ExecutionPlan,
    ExecutionUnit,
    StructuredError,
    UnitResult,
)


# ---------------------------------------------------------------------------
# Unit Execution State
# ---------------------------------------------------------------------------


class UnitExecutionState(Enum):
    """Per-unit execution state tracking."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Bounded Executor
# ---------------------------------------------------------------------------


class BoundedExecutor:
    """
    Runs execution units with configurable global and per-account concurrency
    bounds. Respects prerequisite ordering: a unit only becomes ready when all
    prerequisite units have completed (terminal state). Queues units whose
    prerequisites are not yet complete.

    Catches exceptions at the executor boundary and translates them to failed
    UnitResult with StructuredError. Treats CollectorOutcome.status == "failed"
    as failure (not just exceptions).

    Failed prerequisites cause dependent units to also be marked as failed
    with an appropriate error.
    """

    def __init__(
        self,
        global_concurrency: int = 4,
        per_account_concurrency: int = 4,
    ) -> None:
        self._global_concurrency = global_concurrency
        self._per_account_concurrency = per_account_concurrency

    def execute(
        self,
        plan: ExecutionPlan,
        collector_fn: Callable[[ExecutionUnit, GuardedSession], CollectorOutcome],
        session_factory: SessionFactory,
    ) -> tuple[UnitResult, ...]:
        """
        Execute all units in the plan to terminal state, respecting
        prerequisite ordering and concurrency bounds.

        Returns a tuple of UnitResult in unit ordinal order, regardless
        of completion order.
        """
        units = plan.units
        if not units:
            return ()

        # State tracking
        unit_states: dict[str, UnitExecutionState] = {
            u.unit_id: UnitExecutionState.QUEUED for u in units
        }
        unit_results: dict[str, UnitResult] = {}
        # account_id -> active count. Mutated only from this single
        # orchestrating thread (submission and completion processing both
        # happen here); worker threads only run `_run_unit`, which never
        # touches this dict. No lock is required.
        account_active: dict[str, int] = {}

        def _is_terminal(state: UnitExecutionState) -> bool:
            return state in (UnitExecutionState.SUCCEEDED, UnitExecutionState.FAILED)

        def _prereqs_met(unit: ExecutionUnit) -> bool:
            for prereq_id in unit.prerequisite_unit_ids:
                if prereq_id in unit_states and not _is_terminal(unit_states[prereq_id]):
                    return False
            return True

        def _has_failed_prereq(unit: ExecutionUnit) -> bool:
            for prereq_id in unit.prerequisite_unit_ids:
                if prereq_id in unit_states and unit_states[prereq_id] == UnitExecutionState.FAILED:
                    return True
            return False

        def _can_run(unit: ExecutionUnit) -> bool:
            active = account_active.get(unit.account_id, 0)
            return active < self._per_account_concurrency

        def _run_unit(unit: ExecutionUnit) -> UnitResult:
            """Execute a single unit in the thread pool."""
            try:
                target = AccountTarget(account_id=unit.account_id)
                session = session_factory.for_account(target)
                outcome = collector_fn(unit, session)

                if outcome.status == "failed":
                    return UnitResult(
                        unit_id=unit.unit_id,
                        capability_id=unit.capability_id,
                        account_id=unit.account_id,
                        region_scope=unit.region_scope,
                        status="failed",
                        records_count=len(outcome.records),
                        error=outcome.error,
                        attempts=outcome.attempts,
                    )
                else:
                    return UnitResult(
                        unit_id=unit.unit_id,
                        capability_id=unit.capability_id,
                        account_id=unit.account_id,
                        region_scope=unit.region_scope,
                        status="succeeded",
                        records_count=len(outcome.records),
                        error=None,
                        attempts=outcome.attempts,
                    )
            except Exception as exc:
                return UnitResult(
                    unit_id=unit.unit_id,
                    capability_id=unit.capability_id,
                    account_id=unit.account_id,
                    region_scope=unit.region_scope,
                    status="failed",
                    records_count=0,
                    error=StructuredError(
                        code="EXECUTOR_EXCEPTION",
                        category="internal",
                        retryable=False,
                        safe_message=str(exc)[:200],
                        capability_id=unit.capability_id,
                        account_id=unit.account_id,
                        region_scope=unit.region_scope,
                    ),
                    attempts=1,
                )

        with ThreadPoolExecutor(max_workers=self._global_concurrency) as pool:
            in_flight: dict[str, Any] = {}  # unit_id -> Future

            while True:
                # Mark units with failed prereqs as failed
                changed = True
                while changed:
                    changed = False
                    for unit in units:
                        if unit_states[unit.unit_id] != UnitExecutionState.QUEUED:
                            continue
                        if _has_failed_prereq(unit):
                            unit_states[unit.unit_id] = UnitExecutionState.FAILED
                            unit_results[unit.unit_id] = UnitResult(
                                unit_id=unit.unit_id,
                                capability_id=unit.capability_id,
                                account_id=unit.account_id,
                                region_scope=unit.region_scope,
                                status="failed",
                                records_count=0,
                                error=StructuredError(
                                    code="PREREQUISITE_FAILED",
                                    category="internal",
                                    retryable=False,
                                    safe_message=(
                                        f"Prerequisite unit failed; "
                                        f"unit {unit.unit_id} cannot proceed."
                                    ),
                                    capability_id=unit.capability_id,
                                    account_id=unit.account_id,
                                    region_scope=unit.region_scope,
                                ),
                                attempts=0,
                            )
                            changed = True

                # Check termination
                if all(_is_terminal(unit_states[u.unit_id]) for u in units):
                    break

                # Submit ready units
                for unit in units:
                    if unit_states[unit.unit_id] != UnitExecutionState.QUEUED:
                        continue
                    if not _prereqs_met(unit):
                        continue
                    if not _can_run(unit):
                        continue
                    unit_states[unit.unit_id] = UnitExecutionState.RUNNING
                    account_active[unit.account_id] = (
                        account_active.get(unit.account_id, 0) + 1
                    )
                    future = pool.submit(_run_unit, unit)
                    in_flight[unit.unit_id] = future

                # If nothing in flight and nothing to submit, something is wrong
                if not in_flight:
                    # All remaining units have unmet prereqs but no running units
                    # This means circular dependency or all blocked — mark remaining as failed
                    for unit in units:
                        if unit_states[unit.unit_id] == UnitExecutionState.QUEUED:
                            unit_states[unit.unit_id] = UnitExecutionState.FAILED
                            unit_results[unit.unit_id] = UnitResult(
                                unit_id=unit.unit_id,
                                capability_id=unit.capability_id,
                                account_id=unit.account_id,
                                region_scope=unit.region_scope,
                                status="failed",
                                records_count=0,
                                error=StructuredError(
                                    code="DEADLOCK_DETECTED",
                                    category="internal",
                                    retryable=False,
                                    safe_message="Unit blocked — possible circular dependency.",
                                    capability_id=unit.capability_id,
                                    account_id=unit.account_id,
                                    region_scope=unit.region_scope,
                                ),
                                attempts=0,
                            )
                    break

                # Wait for at least one in-flight to complete
                done_ids: list[str] = []
                for uid, fut in list(in_flight.items()):
                    if fut.done():
                        done_ids.append(uid)

                if not done_ids:
                    # Block until one completes
                    completed_iter = as_completed(list(in_flight.values()))
                    first_done = next(completed_iter)
                    # Find which unit it belongs to
                    for uid, fut in list(in_flight.items()):
                        if fut is first_done:
                            done_ids.append(uid)
                            break

                # Process completed futures
                for uid in done_ids:
                    fut = in_flight.pop(uid)
                    result = fut.result()
                    unit_results[uid] = result
                    if result.status == "succeeded":
                        unit_states[uid] = UnitExecutionState.SUCCEEDED
                    else:
                        unit_states[uid] = UnitExecutionState.FAILED
                    # Find the unit to decrement account active
                    for u in units:
                        if u.unit_id == uid:
                            account_active[u.account_id] = (
                                account_active.get(u.account_id, 0) - 1
                            )
                            break

        # Return results sorted by ordinal for deterministic output
        sorted_results = sorted(
            unit_results.values(),
            key=lambda r: next(
                u.ordinal for u in units if u.unit_id == r.unit_id
            ),
        )
        return tuple(sorted_results)


# ---------------------------------------------------------------------------
# Aggregate Status Views
# ---------------------------------------------------------------------------


def aggregate_run_status(
    unit_results: tuple[UnitResult, ...],
    cancelled: bool = False,
) -> str:
    """
    Derive aggregate run status from immutable unit results.

    - "succeeded" if all units succeeded
    - "partial-success" if at least one succeeded and at least one failed
    - "failed" if no unit succeeded (and at least one failed)
    - "cancelled" only if explicitly cancelled (not derived from results alone)

    Does NOT depend on completion order.
    """
    if cancelled:
        return "cancelled"

    if not unit_results:
        return "succeeded"

    has_success = any(r.status == "succeeded" for r in unit_results)
    has_failure = any(r.status == "failed" for r in unit_results)

    if has_success and has_failure:
        return "partial-success"
    elif has_success:
        return "succeeded"
    elif has_failure:
        return "failed"
    else:
        return "succeeded"


def aggregate_account_status(
    unit_results: tuple[UnitResult, ...],
    account_id: str,
    cancelled: bool = False,
) -> str:
    """
    Derive aggregate status for a specific account from unit results.
    Same logic as run status but filtered to units for that account.
    """
    filtered = tuple(r for r in unit_results if r.account_id == account_id)
    return aggregate_run_status(filtered, cancelled=cancelled)


def aggregate_region_status(
    unit_results: tuple[UnitResult, ...],
    region_scope: str,
    cancelled: bool = False,
) -> str:
    """
    Derive aggregate status for a specific region scope from unit results.
    Same logic as run status but filtered to units for that region.
    """
    filtered = tuple(r for r in unit_results if r.region_scope == region_scope)
    return aggregate_run_status(filtered, cancelled=cancelled)


def aggregate_capability_status(
    unit_results: tuple[UnitResult, ...],
    capability_id: str,
    cancelled: bool = False,
) -> str:
    """
    Derive aggregate status for a specific capability from unit results.
    Same logic as run status but filtered to units for that capability.
    """
    filtered = tuple(r for r in unit_results if r.capability_id == capability_id)
    return aggregate_run_status(filtered, cancelled=cancelled)
