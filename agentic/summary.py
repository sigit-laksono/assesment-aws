"""
Agentic AWS Assessment — Per-Capability Result Summary (Requirement 12).

One pure function that groups UnitResult into a per-(capability, account,
region) succeeded/failed/permission-denied count. No required-item
registry, no completeness ratio, no extra categories — only the three
statuses derivable from CollectorOutcome/UnitResult.
"""

from __future__ import annotations

from typing import Sequence

from agentic.models import CapabilitySummary, UnitResult


def summarize(unit_results: Sequence[UnitResult]) -> tuple[CapabilitySummary, ...]:
    """
    Build one CapabilitySummary per (capability_id, account_id, region_scope).

    Each UnitResult maps to exactly one summary row (Task 5.1's planner
    creates exactly one unit per capability-target pair, so there is no
    aggregation across rows to perform). A failed unit whose error category
    is "permission-denied" is reported as such rather than a generic
    failure; a succeeded unit keeps its record_count even when zero
    (Requirement 12.2).
    """
    summaries: list[CapabilitySummary] = []
    for result in unit_results:
        if result.status == "succeeded":
            status = "succeeded"
        elif result.error is not None and result.error.category == "permission-denied":
            status = "permission-denied"
        else:
            status = "failed"

        summaries.append(
            CapabilitySummary(
                capability_id=result.capability_id,
                account_id=result.account_id,
                region_scope=result.region_scope,
                status=status,
                record_count=result.records_count,
            )
        )
    return tuple(summaries)


if __name__ == "__main__":
    # ponytail: minimal runnable self-check; full coverage lands in Task 7.3.
    from agentic.models import StructuredError

    results = (
        UnitResult(
            capability_id="ec2.inventory",
            account_id="111111111111",
            region_scope="us-east-1",
            status="succeeded",
            records_count=0,
        ),
        UnitResult(
            capability_id="s3.inventory",
            account_id="111111111111",
            region_scope="aws-global",
            status="failed",
            records_count=0,
            error=StructuredError(category="permission-denied"),
        ),
        UnitResult(
            capability_id="iam.identity",
            account_id="111111111111",
            region_scope="aws-global",
            status="failed",
            records_count=0,
            error=StructuredError(category="internal"),
        ),
    )
    out = summarize(results)
    assert len(out) == 3
    assert out[0].status == "succeeded" and out[0].record_count == 0
    assert out[1].status == "permission-denied"
    assert out[2].status == "failed"
    print("summarize() self-check passed")
