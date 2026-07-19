"""
Tests for agentic.summary.summarize (Requirement 12.1, 12.2).

Covers:
- Mixed succeeded / failed (generic) / failed (permission-denied) UnitResults
  produce the correct CapabilitySummary status for each.
- A succeeded UnitResult with records_count=0 stays "succeeded" with
  record_count=0 (Requirement 12.2), not "failed".
- summarize(()) returns an empty tuple.
"""

from __future__ import annotations

from agentic.models import StructuredError, UnitResult
from agentic.summary import summarize


class TestSummarizeStatusMapping:
    """Status classification per (capability, account, region) row."""

    def test_mixed_statuses_classified_correctly(self):
        results = (
            UnitResult(
                unit_id="u1",
                capability_id="ec2.inventory",
                account_id="111111111111",
                region_scope="us-east-1",
                status="succeeded",
                records_count=5,
            ),
            UnitResult(
                unit_id="u2",
                capability_id="iam.identity",
                account_id="111111111111",
                region_scope="aws-global",
                status="failed",
                records_count=0,
                error=StructuredError(category="internal"),
            ),
            UnitResult(
                unit_id="u3",
                capability_id="s3.inventory",
                account_id="111111111111",
                region_scope="aws-global",
                status="failed",
                records_count=0,
                error=StructuredError(category="permission-denied"),
            ),
        )

        out = summarize(results)

        assert len(out) == 3
        assert out[0].status == "succeeded"
        assert out[0].record_count == 5
        assert out[1].status == "failed"
        assert out[2].status == "permission-denied"

    def test_failed_without_error_is_generic_failed(self):
        """A failed unit with no error attached still maps to 'failed'."""
        results = (
            UnitResult(
                unit_id="u1",
                capability_id="ec2.inventory",
                account_id="111111111111",
                region_scope="us-east-1",
                status="failed",
                records_count=0,
                error=None,
            ),
        )

        out = summarize(results)

        assert out[0].status == "failed"

    def test_succeeded_zero_records_stays_succeeded(self):
        """Requirement 12.2: a successful empty result is not a failure."""
        results = (
            UnitResult(
                unit_id="u1",
                capability_id="ec2.inventory",
                account_id="111111111111",
                region_scope="us-east-1",
                status="succeeded",
                records_count=0,
            ),
        )

        out = summarize(results)

        assert len(out) == 1
        assert out[0].status == "succeeded"
        assert out[0].record_count == 0

    def test_fields_propagate_from_unit_result(self):
        results = (
            UnitResult(
                unit_id="u1",
                capability_id="ec2.inventory",
                account_id="222222222222",
                region_scope="eu-west-1",
                status="succeeded",
                records_count=3,
            ),
        )

        out = summarize(results)

        assert out[0].capability_id == "ec2.inventory"
        assert out[0].account_id == "222222222222"
        assert out[0].region_scope == "eu-west-1"


class TestSummarizeEmptyInput:
    def test_empty_input_returns_empty_tuple(self):
        assert summarize(()) == ()
