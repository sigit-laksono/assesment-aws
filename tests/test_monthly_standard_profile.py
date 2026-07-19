"""
Unit tests for monthly-standard@1.0.0 Assessment Profile.

Verifies the profile artifact meets design requirements:
- Status is "draft" (Req 5.1, 5.5)
- Contains all required capability items (Req 15.4, 16.3)
- Completeness threshold = Decimal("1.0")
- Region rule mode is "discovery"
- Collection window period_type is "monthly"
- All items have non-empty capability_id, capability_version,
  required_fields, and required_permissions (Req 10.1)
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from agentic.profiles import create_monthly_standard_v1


# ---------------------------------------------------------------------------
# Expected capability IDs
# ---------------------------------------------------------------------------

EXPECTED_GLOBAL_IDS = {
    "billing.summary",
    "s3.inventory",
    "cloudfront.inventory",
    "route53.inventory",
    "iam.inventory",
}

EXPECTED_REGIONAL_IDS = {
    "ec2.inventory",
    "ebs.inventory",
    "efs.inventory",
    "backup.inventory",
    "lambda.inventory",
    "eks.inventory",
    "ecr.inventory",
    "alb.inventory",
    "nlb.inventory",
    "vpc.inventory",
    "nat.inventory",
    "rds.inventory",
    "dynamodb.inventory",
    "elasticache.inventory",
    "kms.inventory",
    "waf.inventory",
    "secretsmanager.inventory",
    "cloudwatch.inventory",
    "cloudtrail.inventory",
    "config.inventory",
    "sns.inventory",
    "msk.inventory",
    "amazonmq.inventory",
    "glue.inventory",
}

EXPECTED_DERIVED_IDS = {
    "cost-optimization.findings",
}

ALL_EXPECTED_IDS = EXPECTED_GLOBAL_IDS | EXPECTED_REGIONAL_IDS | EXPECTED_DERIVED_IDS


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMonthlyStandardProfile:
    """Tests for the monthly-standard@1.0.0 profile artifact."""

    def test_status_is_draft(self) -> None:
        """Profile MUST be in draft status until all capabilities pass readiness."""
        profile = create_monthly_standard_v1()
        assert profile.status == "draft"

    def test_profile_id_and_version(self) -> None:
        """Profile has correct identity."""
        profile = create_monthly_standard_v1()
        assert profile.profile_id == "monthly-standard"
        assert str(profile.version) == "1.0.0"

    def test_items_nonempty(self) -> None:
        """Profile MUST have a non-empty list of required items."""
        profile = create_monthly_standard_v1()
        assert len(profile.items) > 0

    def test_completeness_threshold(self) -> None:
        """Completeness threshold must be Decimal('1.0')."""
        profile = create_monthly_standard_v1()
        assert profile.completeness_threshold == Decimal("1.0")

    def test_region_rule_discovery(self) -> None:
        """Region rule mode must be 'discovery'."""
        profile = create_monthly_standard_v1()
        assert profile.region_rule.mode == "discovery"

    def test_collection_window_monthly(self) -> None:
        """Collection window period_type must be 'monthly'."""
        profile = create_monthly_standard_v1()
        assert profile.collection_window.period_type == "monthly"

    def test_all_items_have_nonempty_capability_id(self) -> None:
        """Every item must have a non-empty capability_id."""
        profile = create_monthly_standard_v1()
        for item in profile.items:
            assert item.capability_id, f"Empty capability_id in item: {item}"

    def test_all_items_have_nonempty_capability_version(self) -> None:
        """Every item must have a non-empty capability_version."""
        profile = create_monthly_standard_v1()
        for item in profile.items:
            assert item.capability_version, (
                f"Empty capability_version for {item.capability_id}"
            )

    def test_all_items_have_nonempty_required_fields(self) -> None:
        """Every item must declare at least one required field."""
        profile = create_monthly_standard_v1()
        for item in profile.items:
            assert item.required_fields, (
                f"Empty required_fields for {item.capability_id}"
            )

    def test_all_items_have_nonempty_required_permissions(self) -> None:
        """Every item must declare at least one required permission (Req 10.1)."""
        profile = create_monthly_standard_v1()
        for item in profile.items:
            assert item.required_permissions, (
                f"Empty required_permissions for {item.capability_id}"
            )

    def test_contains_all_expected_capability_ids(self) -> None:
        """Profile must enumerate ALL required capability IDs from the design."""
        profile = create_monthly_standard_v1()
        actual_ids = {item.capability_id for item in profile.items}
        missing = ALL_EXPECTED_IDS - actual_ids
        assert not missing, f"Missing capability IDs: {missing}"

    def test_global_items_have_global_scope(self) -> None:
        """Global capabilities must have target_scope='global'."""
        profile = create_monthly_standard_v1()
        for item in profile.items:
            if item.capability_id in EXPECTED_GLOBAL_IDS:
                assert item.target_scope == "global", (
                    f"{item.capability_id} should be global"
                )

    def test_regional_items_have_regional_scope(self) -> None:
        """Regional capabilities must have target_scope='regional'."""
        profile = create_monthly_standard_v1()
        for item in profile.items:
            if item.capability_id in EXPECTED_REGIONAL_IDS:
                assert item.target_scope == "regional", (
                    f"{item.capability_id} should be regional"
                )

    def test_derived_items_have_derived_scope(self) -> None:
        """Derived capabilities must have target_scope='derived'."""
        profile = create_monthly_standard_v1()
        for item in profile.items:
            if item.capability_id in EXPECTED_DERIVED_IDS:
                assert item.target_scope == "derived", (
                    f"{item.capability_id} should be derived"
                )

    def test_regional_items_have_not_applicable_rule(self) -> None:
        """Regional items should declare a not-applicable rule for unsupported regions."""
        profile = create_monthly_standard_v1()
        for item in profile.items:
            if item.capability_id in EXPECTED_REGIONAL_IDS:
                assert item.not_applicable_rule == "service-not-available-in-region", (
                    f"{item.capability_id} missing not_applicable_rule"
                )

    def test_total_item_count(self) -> None:
        """Profile should have exactly 30 items (5 global + 24 regional + 1 derived)."""
        profile = create_monthly_standard_v1()
        assert len(profile.items) == 30
