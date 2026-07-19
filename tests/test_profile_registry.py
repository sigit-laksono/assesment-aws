"""
Unit tests for AssessmentProfileRegistryImpl.

Tests cover:
- Exact-version resolution (Req 5.2)
- Immutable publication with content digest
- Duplicate prevention (idempotent same content, reject different content)
- Major-version compatibility rules (Req 5.3)
- resolve_compatible returns latest minor/patch within same major
- Validation: nonempty items, fields, permissions, collection window, threshold
- Lifecycle status transitions
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from agentic.models import (
    AssessmentProfile,
    CollectionWindow,
    RegionRule,
    RequiredProfileItem,
    SemVer,
    StructuredError,
)
from agentic.profile_registry import (
    AssessmentProfileRegistryImpl,
    ProfilePublicationError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_valid_profile(
    profile_id: str = "monthly-standard",
    version: SemVer | None = None,
    status: str = "draft",
    items: tuple[RequiredProfileItem, ...] | None = None,
    region_rule: RegionRule | None = None,
    collection_window: CollectionWindow | None = None,
    completeness_threshold: Decimal = Decimal("1.0"),
) -> AssessmentProfile:
    """Create a valid AssessmentProfile for testing."""
    if version is None:
        version = SemVer(1, 0, 0)
    if items is None:
        items = (
            RequiredProfileItem(
                capability_id="ec2.inventory",
                capability_version="1.0.0",
                required_fields=("instance_id", "account_id"),
                target_scope="regional",
                required_permissions=("ec2:DescribeInstances",),
            ),
        )
    if region_rule is None:
        region_rule = RegionRule(mode="explicit", explicit_regions=("us-east-1",))
    if collection_window is None:
        collection_window = CollectionWindow(
            period_type="monthly", start="2024-01-01T00:00:00Z", end="2024-01-31T23:59:59Z"
        )

    return AssessmentProfile(
        profile_id=profile_id,
        version=version,
        effective_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        status=status,
        items=items,
        region_rule=region_rule,
        collection_window=collection_window,
        completeness_threshold=completeness_threshold,
    )


# ---------------------------------------------------------------------------
# Publication Tests
# ---------------------------------------------------------------------------


class TestPublish:
    """Tests for the publish() method."""

    def test_publish_valid_profile_returns_digest(self):
        registry = AssessmentProfileRegistryImpl()
        profile = _make_valid_profile()
        digest = registry.publish(profile)
        assert isinstance(digest, str)
        assert len(digest) == 64  # SHA-256 hex

    def test_publish_same_content_is_idempotent(self):
        registry = AssessmentProfileRegistryImpl()
        profile = _make_valid_profile()
        digest1 = registry.publish(profile)
        digest2 = registry.publish(profile)
        assert digest1 == digest2

    def test_publish_different_content_same_version_rejected(self):
        registry = AssessmentProfileRegistryImpl()
        profile1 = _make_valid_profile()
        registry.publish(profile1)

        # Same version but different items
        profile2 = _make_valid_profile(
            items=(
                RequiredProfileItem(
                    capability_id="s3.inventory",
                    capability_version="1.0.0",
                    required_fields=("bucket_name",),
                    target_scope="global",
                    required_permissions=("s3:ListBuckets",),
                ),
            )
        )
        with pytest.raises(ProfilePublicationError) as exc_info:
            registry.publish(profile2)
        assert "immutable" in exc_info.value.reasons[0].lower() or "different" in exc_info.value.reasons[0].lower()

    def test_publish_computes_consistent_digest(self):
        """Same canonical content always produces same digest."""
        registry1 = AssessmentProfileRegistryImpl()
        registry2 = AssessmentProfileRegistryImpl()
        profile = _make_valid_profile()
        digest1 = registry1.publish(profile)
        digest2 = registry2.publish(profile)
        assert digest1 == digest2


# ---------------------------------------------------------------------------
# Validation Tests
# ---------------------------------------------------------------------------


class TestValidation:
    """Tests for profile validation on publish."""

    def test_reject_empty_items(self):
        registry = AssessmentProfileRegistryImpl()
        profile = _make_valid_profile(items=())
        with pytest.raises(ProfilePublicationError) as exc_info:
            registry.publish(profile)
        assert "at least one required item" in exc_info.value.reasons[0].lower()

    def test_reject_item_without_capability_id(self):
        registry = AssessmentProfileRegistryImpl()
        profile = _make_valid_profile(
            items=(
                RequiredProfileItem(
                    capability_id="",
                    capability_version="1.0.0",
                    required_fields=("field_a",),
                    required_permissions=("perm_a",),
                ),
            )
        )
        with pytest.raises(ProfilePublicationError) as exc_info:
            registry.publish(profile)
        assert "capability_id" in exc_info.value.reasons[0]

    def test_reject_item_without_capability_version(self):
        registry = AssessmentProfileRegistryImpl()
        profile = _make_valid_profile(
            items=(
                RequiredProfileItem(
                    capability_id="ec2.inventory",
                    capability_version="",
                    required_fields=("field_a",),
                    required_permissions=("perm_a",),
                ),
            )
        )
        with pytest.raises(ProfilePublicationError) as exc_info:
            registry.publish(profile)
        assert "capability_version" in exc_info.value.reasons[0]

    def test_reject_item_without_required_fields(self):
        registry = AssessmentProfileRegistryImpl()
        profile = _make_valid_profile(
            items=(
                RequiredProfileItem(
                    capability_id="ec2.inventory",
                    capability_version="1.0.0",
                    required_fields=(),
                    required_permissions=("perm_a",),
                ),
            )
        )
        with pytest.raises(ProfilePublicationError) as exc_info:
            registry.publish(profile)
        assert "required_fields" in exc_info.value.reasons[0]

    def test_reject_item_without_required_permissions(self):
        registry = AssessmentProfileRegistryImpl()
        profile = _make_valid_profile(
            items=(
                RequiredProfileItem(
                    capability_id="ec2.inventory",
                    capability_version="1.0.0",
                    required_fields=("field_a",),
                    required_permissions=(),
                ),
            )
        )
        with pytest.raises(ProfilePublicationError) as exc_info:
            registry.publish(profile)
        assert "required_permissions" in exc_info.value.reasons[0]

    def test_reject_invalid_completeness_threshold_above_one(self):
        registry = AssessmentProfileRegistryImpl()
        profile = _make_valid_profile(completeness_threshold=Decimal("1.5"))
        with pytest.raises(ProfilePublicationError) as exc_info:
            registry.publish(profile)
        assert "completeness_threshold" in exc_info.value.reasons[0]

    def test_reject_invalid_completeness_threshold_below_zero(self):
        registry = AssessmentProfileRegistryImpl()
        profile = _make_valid_profile(completeness_threshold=Decimal("-0.1"))
        with pytest.raises(ProfilePublicationError) as exc_info:
            registry.publish(profile)
        assert "completeness_threshold" in exc_info.value.reasons[0]

    def test_accept_completeness_threshold_zero(self):
        registry = AssessmentProfileRegistryImpl()
        profile = _make_valid_profile(completeness_threshold=Decimal("0"))
        digest = registry.publish(profile)
        assert isinstance(digest, str)

    def test_accept_completeness_threshold_one(self):
        registry = AssessmentProfileRegistryImpl()
        profile = _make_valid_profile(completeness_threshold=Decimal("1.0"))
        digest = registry.publish(profile)
        assert isinstance(digest, str)


# ---------------------------------------------------------------------------
# Resolution Tests
# ---------------------------------------------------------------------------


class TestResolve:
    """Tests for the resolve() method."""

    def test_resolve_exact_version(self):
        registry = AssessmentProfileRegistryImpl()
        profile = _make_valid_profile()
        registry.publish(profile)

        result = registry.resolve("monthly-standard", "1.0.0")
        assert isinstance(result, AssessmentProfile)
        assert result.profile_id == "monthly-standard"
        assert result.version == SemVer(1, 0, 0)

    def test_resolve_unknown_profile_returns_error(self):
        registry = AssessmentProfileRegistryImpl()
        result = registry.resolve("nonexistent", "1.0.0")
        assert isinstance(result, StructuredError)
        assert result.code == "PROFILE_NOT_FOUND"

    def test_resolve_unknown_version_returns_error(self):
        registry = AssessmentProfileRegistryImpl()
        profile = _make_valid_profile()
        registry.publish(profile)

        result = registry.resolve("monthly-standard", "2.0.0")
        assert isinstance(result, StructuredError)
        assert result.code == "PROFILE_NOT_FOUND"

    def test_resolved_profile_is_immutable(self):
        """Resolved profile content is frozen (immutable dataclass)."""
        registry = AssessmentProfileRegistryImpl()
        profile = _make_valid_profile()
        registry.publish(profile)

        resolved = registry.resolve("monthly-standard", "1.0.0")
        assert isinstance(resolved, AssessmentProfile)
        with pytest.raises(Exception):
            resolved.profile_id = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# resolve_compatible Tests
# ---------------------------------------------------------------------------


class TestResolveCompatible:
    """Tests for the resolve_compatible() method."""

    def test_resolve_compatible_returns_latest_in_major(self):
        registry = AssessmentProfileRegistryImpl()

        # Publish 1.0.0
        profile_100 = _make_valid_profile(version=SemVer(1, 0, 0))
        registry.publish(profile_100)

        # Publish 1.1.0 (compatible addition)
        profile_110 = _make_valid_profile(
            version=SemVer(1, 1, 0),
            items=(
                RequiredProfileItem(
                    capability_id="ec2.inventory",
                    capability_version="1.0.0",
                    required_fields=("instance_id", "account_id"),
                    target_scope="regional",
                    required_permissions=("ec2:DescribeInstances",),
                ),
            ),
        )
        registry.publish(profile_110)

        result = registry.resolve_compatible("monthly-standard", 1)
        assert isinstance(result, AssessmentProfile)
        assert result.version == SemVer(1, 1, 0)

    def test_resolve_compatible_unknown_profile_returns_error(self):
        registry = AssessmentProfileRegistryImpl()
        result = registry.resolve_compatible("nonexistent", 1)
        assert isinstance(result, StructuredError)
        assert result.code == "PROFILE_NOT_FOUND"

    def test_resolve_compatible_unknown_major_returns_error(self):
        registry = AssessmentProfileRegistryImpl()
        profile = _make_valid_profile()
        registry.publish(profile)

        result = registry.resolve_compatible("monthly-standard", 5)
        assert isinstance(result, StructuredError)
        assert result.code == "PROFILE_NOT_FOUND"


# ---------------------------------------------------------------------------
# Major-Version Compatibility Tests (Req 5.3)
# ---------------------------------------------------------------------------


class TestMajorVersionCompatibility:
    """Tests that incompatible changes require a new major version."""

    def test_reject_capability_change_within_same_major(self):
        registry = AssessmentProfileRegistryImpl()
        profile_100 = _make_valid_profile(version=SemVer(1, 0, 0))
        registry.publish(profile_100)

        # Try to publish 1.1.0 with different capabilities (incompatible)
        profile_110 = _make_valid_profile(
            version=SemVer(1, 1, 0),
            items=(
                RequiredProfileItem(
                    capability_id="s3.inventory",
                    capability_version="1.0.0",
                    required_fields=("bucket_name",),
                    target_scope="global",
                    required_permissions=("s3:ListBuckets",),
                ),
            ),
        )
        with pytest.raises(ProfilePublicationError) as exc_info:
            registry.publish(profile_110)
        assert "incompatible" in exc_info.value.reasons[0].lower()

    def test_reject_region_rule_change_within_same_major(self):
        registry = AssessmentProfileRegistryImpl()
        profile_100 = _make_valid_profile(version=SemVer(1, 0, 0))
        registry.publish(profile_100)

        # Try to publish 1.1.0 with different region rule
        profile_110 = _make_valid_profile(
            version=SemVer(1, 1, 0),
            region_rule=RegionRule(mode="discovery"),
        )
        with pytest.raises(ProfilePublicationError) as exc_info:
            registry.publish(profile_110)
        assert "incompatible" in exc_info.value.reasons[0].lower()

    def test_reject_completeness_threshold_change_within_same_major(self):
        registry = AssessmentProfileRegistryImpl()
        profile_100 = _make_valid_profile(
            version=SemVer(1, 0, 0), completeness_threshold=Decimal("1.0")
        )
        registry.publish(profile_100)

        # Try to publish 1.1.0 with different completeness threshold
        profile_110 = _make_valid_profile(
            version=SemVer(1, 1, 0), completeness_threshold=Decimal("0.8")
        )
        with pytest.raises(ProfilePublicationError) as exc_info:
            registry.publish(profile_110)
        assert "incompatible" in exc_info.value.reasons[0].lower()

    def test_allow_incompatible_changes_with_new_major_version(self):
        registry = AssessmentProfileRegistryImpl()
        profile_100 = _make_valid_profile(version=SemVer(1, 0, 0))
        registry.publish(profile_100)

        # Publish 2.0.0 with different capabilities — allowed
        profile_200 = _make_valid_profile(
            version=SemVer(2, 0, 0),
            items=(
                RequiredProfileItem(
                    capability_id="s3.inventory",
                    capability_version="1.0.0",
                    required_fields=("bucket_name",),
                    target_scope="global",
                    required_permissions=("s3:ListBuckets",),
                ),
            ),
        )
        digest = registry.publish(profile_200)
        assert isinstance(digest, str)
        assert len(digest) == 64


# ---------------------------------------------------------------------------
# Lifecycle Tests
# ---------------------------------------------------------------------------


class TestLifecycle:
    """Tests for lifecycle status transition rules."""

    def test_publish_draft_profile(self):
        registry = AssessmentProfileRegistryImpl()
        profile = _make_valid_profile(status="draft")
        digest = registry.publish(profile)
        assert isinstance(digest, str)

    def test_reject_revert_from_retired(self):
        """Cannot publish a non-retired version after a retired one at same major."""
        registry = AssessmentProfileRegistryImpl()

        # Publish 1.0.0 as retired
        profile_retired = _make_valid_profile(
            version=SemVer(1, 0, 0), status="retired"
        )
        registry.publish(profile_retired)

        # Try to publish 1.1.0 as draft (revert) — should be rejected
        profile_draft = _make_valid_profile(
            version=SemVer(1, 1, 0), status="draft"
        )
        with pytest.raises(ProfilePublicationError):
            registry.publish(profile_draft)

    def test_allow_new_major_after_retired(self):
        """A new major version can start fresh after retirement."""
        registry = AssessmentProfileRegistryImpl()

        # Publish 1.0.0 as retired
        profile_retired = _make_valid_profile(
            version=SemVer(1, 0, 0), status="retired"
        )
        registry.publish(profile_retired)

        # Publish 2.0.0 as draft — allowed because new major
        profile_new = _make_valid_profile(
            version=SemVer(2, 0, 0),
            status="draft",
            items=(
                RequiredProfileItem(
                    capability_id="s3.inventory",
                    capability_version="1.0.0",
                    required_fields=("bucket_name",),
                    target_scope="global",
                    required_permissions=("s3:ListBuckets",),
                ),
            ),
        )
        digest = registry.publish(profile_new)
        assert isinstance(digest, str)


# ---------------------------------------------------------------------------
# Error Conversion Tests
# ---------------------------------------------------------------------------


class TestErrorConversion:
    """Tests for error-to-StructuredError conversion."""

    def test_publication_error_to_structured_error(self):
        err = ProfilePublicationError(
            profile_id="test",
            version="1.0.0",
            reasons=["items must not be empty"],
        )
        se = err.to_structured_error()
        assert isinstance(se, StructuredError)
        assert se.code == "PROFILE_PUBLICATION_REJECTED"
        assert se.category == "validation"
        assert se.retryable is False
        assert "items must not be empty" in se.safe_message
