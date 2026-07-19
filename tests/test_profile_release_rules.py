"""
Profile Release Rules — Additional unit tests complementing test_profile_registry.py.

Tests cover:
- Baseline profile nonempty (Req 5.1)
- Exact artifact deterministic publication
- Incompatible changes require major version (Req 5.3)
- Draft profile cannot be activated for monthly-assessment
- Schema version requirement (Req 3.6)

Requirements: 3.6, 5.1, 5.2, 5.3
"""

from __future__ import annotations

import os
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from agentic.models import (
    AccountTarget,
    AssessmentProfile,
    CapabilityDescriptor,
    CapabilityRequest,
    CollectionWindow,
    ExecutionContext,
    InvocationRequest,
    RegionRule,
    RequiredProfileItem,
    SemVer,
    StructuredError,
)
from agentic.orchestrator import invoke
from agentic.profile_registry import (
    AssessmentProfileRegistryImpl,
    ProfilePublicationError,
)
from agentic.profiles import create_monthly_standard_v1
from agentic.registry import CapabilityRegistryImpl
from agentic.schemas.processor import CanonicalSchemaProcessor


# ---------------------------------------------------------------------------
# TestBaselineProfileContent (Req 5.1)
# ---------------------------------------------------------------------------


class TestBaselineProfileContent:
    """Baseline profile artifact validation tests."""

    def test_monthly_standard_v1_has_nonempty_items(self):
        """Verify the monthly-standard@1.0.0 profile artifact has nonempty items."""
        profile = create_monthly_standard_v1()
        assert len(profile.items) > 0, "Baseline profile must have at least one item"

    def test_monthly_standard_v1_publishable(self):
        """Verify it can be published to a registry successfully."""
        registry = AssessmentProfileRegistryImpl()
        profile = create_monthly_standard_v1()
        digest = registry.publish(profile)
        assert isinstance(digest, str)
        assert len(digest) == 64  # SHA-256 hex digest

    def test_monthly_standard_v1_contains_all_scope_categories(self):
        """Verify it contains all expected scope categories (global, regional, derived)."""
        profile = create_monthly_standard_v1()
        scopes = {item.target_scope for item in profile.items}
        assert "global" in scopes, "Profile must contain global scope items"
        assert "regional" in scopes, "Profile must contain regional scope items"
        assert "derived" in scopes, "Profile must contain derived scope items"

    def test_monthly_standard_v1_has_expected_profile_id(self):
        """Verify profile_id and version are set correctly."""
        profile = create_monthly_standard_v1()
        assert profile.profile_id == "monthly-standard"
        assert profile.version == SemVer(1, 0, 0)

    def test_monthly_standard_v1_is_draft(self):
        """Verify the baseline profile starts in draft status."""
        profile = create_monthly_standard_v1()
        assert profile.status == "draft"


# ---------------------------------------------------------------------------
# TestDeterministicArtifact (Req 5.2)
# ---------------------------------------------------------------------------


class TestDeterministicArtifact:
    """Tests that profile publication is deterministic."""

    def test_same_profile_two_independent_registries_same_digest(self):
        """Publish the same profile to two independent registries and verify same digest."""
        profile = create_monthly_standard_v1()
        registry1 = AssessmentProfileRegistryImpl()
        registry2 = AssessmentProfileRegistryImpl()

        digest1 = registry1.publish(profile)
        digest2 = registry2.publish(profile)

        assert digest1 == digest2, (
            "Same profile published to two independent registries must produce "
            "the same content digest"
        )

    def test_resolve_returns_byte_equivalent_content(self):
        """Verify resolving the published profile returns equivalent content."""
        profile = create_monthly_standard_v1()
        registry = AssessmentProfileRegistryImpl()
        registry.publish(profile)

        resolved = registry.resolve("monthly-standard", "1.0.0")
        assert isinstance(resolved, AssessmentProfile)
        assert resolved == profile, (
            "Resolved profile must be byte-equivalent to published profile"
        )

    def test_content_digest_stable_across_multiple_calls(self):
        """Verify the profile content digest is stable across multiple calls."""
        profile = create_monthly_standard_v1()
        registry = AssessmentProfileRegistryImpl()

        digest1 = registry.publish(profile)
        # Idempotent re-publish returns same digest
        digest2 = registry.publish(profile)
        # Compute digest independently
        digest3 = registry._compute_content_digest(profile)

        assert digest1 == digest2
        assert digest1 == digest3, (
            "Content digest must be stable across multiple computations"
        )


# ---------------------------------------------------------------------------
# TestIncompatibleChangeRequiresNewMajor (Req 5.3)
# ---------------------------------------------------------------------------


class TestIncompatibleChangeRequiresNewMajor:
    """Tests that incompatible changes require a new major version."""

    def _make_base_profile(self) -> AssessmentProfile:
        """Create a base profile for incompatibility tests."""
        return AssessmentProfile(
            schema_id="assessment-profile",
            schema_version="1.0.0",
            profile_id="compat-test",
            version=SemVer(1, 0, 0),
            status="draft",
            items=(
                RequiredProfileItem(
                    capability_id="ec2.inventory",
                    capability_version="1.0.0",
                    required_fields=("instance_id", "account_id", "region"),
                    target_scope="regional",
                    required_permissions=("ec2:DescribeInstances",),
                ),
                RequiredProfileItem(
                    capability_id="s3.inventory",
                    capability_version="1.0.0",
                    required_fields=("bucket_name", "account_id"),
                    target_scope="global",
                    required_permissions=("s3:ListAllMyBuckets",),
                ),
            ),
            region_rule=RegionRule(mode="explicit", explicit_regions=("us-east-1",)),
            collection_window=CollectionWindow(period_type="monthly"),
            completeness_threshold=Decimal("0.9"),
        )

    def test_changing_required_capability_list_same_major_rejected(self):
        """Changing required capability list within same major → rejected."""
        registry = AssessmentProfileRegistryImpl()
        base = self._make_base_profile()
        registry.publish(base)

        # Add a new capability in minor version bump
        modified = AssessmentProfile(
            schema_id="assessment-profile",
            schema_version="1.0.0",
            profile_id="compat-test",
            version=SemVer(1, 1, 0),
            status="draft",
            items=(
                RequiredProfileItem(
                    capability_id="ec2.inventory",
                    capability_version="1.0.0",
                    required_fields=("instance_id", "account_id", "region"),
                    target_scope="regional",
                    required_permissions=("ec2:DescribeInstances",),
                ),
                RequiredProfileItem(
                    capability_id="s3.inventory",
                    capability_version="1.0.0",
                    required_fields=("bucket_name", "account_id"),
                    target_scope="global",
                    required_permissions=("s3:ListAllMyBuckets",),
                ),
                RequiredProfileItem(
                    capability_id="rds.inventory",
                    capability_version="1.0.0",
                    required_fields=("db_instance_identifier",),
                    target_scope="regional",
                    required_permissions=("rds:DescribeDBInstances",),
                ),
            ),
            region_rule=RegionRule(mode="explicit", explicit_regions=("us-east-1",)),
            collection_window=CollectionWindow(period_type="monthly"),
            completeness_threshold=Decimal("0.9"),
        )

        with pytest.raises(ProfilePublicationError) as exc_info:
            registry.publish(modified)
        assert "incompatible" in exc_info.value.reasons[0].lower()

    def test_changing_required_field_set_same_major_rejected(self):
        """Changing required field set within same major → rejected."""
        registry = AssessmentProfileRegistryImpl()
        base = self._make_base_profile()
        registry.publish(base)

        # Modify required_fields for ec2.inventory
        modified = AssessmentProfile(
            schema_id="assessment-profile",
            schema_version="1.0.0",
            profile_id="compat-test",
            version=SemVer(1, 1, 0),
            status="draft",
            items=(
                RequiredProfileItem(
                    capability_id="ec2.inventory",
                    capability_version="1.0.0",
                    required_fields=("instance_id", "account_id", "region", "instance_type"),
                    target_scope="regional",
                    required_permissions=("ec2:DescribeInstances",),
                ),
                RequiredProfileItem(
                    capability_id="s3.inventory",
                    capability_version="1.0.0",
                    required_fields=("bucket_name", "account_id"),
                    target_scope="global",
                    required_permissions=("s3:ListAllMyBuckets",),
                ),
            ),
            region_rule=RegionRule(mode="explicit", explicit_regions=("us-east-1",)),
            collection_window=CollectionWindow(period_type="monthly"),
            completeness_threshold=Decimal("0.9"),
        )

        with pytest.raises(ProfilePublicationError) as exc_info:
            registry.publish(modified)
        assert "incompatible" in exc_info.value.reasons[0].lower()

    def test_changing_region_scope_rule_same_major_rejected(self):
        """Changing region scope rule within same major → rejected."""
        registry = AssessmentProfileRegistryImpl()
        base = self._make_base_profile()
        registry.publish(base)

        # Change region rule from explicit to discovery
        modified = AssessmentProfile(
            schema_id="assessment-profile",
            schema_version="1.0.0",
            profile_id="compat-test",
            version=SemVer(1, 1, 0),
            status="draft",
            items=base.items,
            region_rule=RegionRule(mode="discovery"),
            collection_window=CollectionWindow(period_type="monthly"),
            completeness_threshold=Decimal("0.9"),
        )

        with pytest.raises(ProfilePublicationError) as exc_info:
            registry.publish(modified)
        assert "incompatible" in exc_info.value.reasons[0].lower()

    def test_changing_completeness_threshold_same_major_rejected(self):
        """Changing completeness threshold within same major → rejected."""
        registry = AssessmentProfileRegistryImpl()
        base = self._make_base_profile()
        registry.publish(base)

        # Change completeness from 0.9 to 0.8
        modified = AssessmentProfile(
            schema_id="assessment-profile",
            schema_version="1.0.0",
            profile_id="compat-test",
            version=SemVer(1, 1, 0),
            status="draft",
            items=base.items,
            region_rule=RegionRule(mode="explicit", explicit_regions=("us-east-1",)),
            collection_window=CollectionWindow(period_type="monthly"),
            completeness_threshold=Decimal("0.8"),
        )

        with pytest.raises(ProfilePublicationError) as exc_info:
            registry.publish(modified)
        assert "incompatible" in exc_info.value.reasons[0].lower()

    def test_all_incompatible_changes_at_new_major_accepted(self):
        """All the above changes at a new major version → accepted."""
        registry = AssessmentProfileRegistryImpl()
        base = self._make_base_profile()
        registry.publish(base)

        # Version 2.0.0 with all incompatible changes
        new_major = AssessmentProfile(
            schema_id="assessment-profile",
            schema_version="1.0.0",
            profile_id="compat-test",
            version=SemVer(2, 0, 0),
            status="draft",
            items=(
                RequiredProfileItem(
                    capability_id="rds.inventory",
                    capability_version="2.0.0",
                    required_fields=("db_instance_identifier", "engine", "region"),
                    target_scope="regional",
                    required_permissions=("rds:DescribeDBInstances",),
                ),
            ),
            region_rule=RegionRule(mode="discovery"),
            collection_window=CollectionWindow(period_type="weekly"),
            completeness_threshold=Decimal("0.7"),
        )

        digest = registry.publish(new_major)
        assert isinstance(digest, str)
        assert len(digest) == 64


# ---------------------------------------------------------------------------
# TestDraftProfileActivation
# ---------------------------------------------------------------------------


class TestDraftProfileActivation:
    """Tests that draft profiles cannot be used for monthly-assessment."""

    def _make_simple_draft_profile(self) -> AssessmentProfile:
        """Create a simple draft profile for activation tests."""
        return AssessmentProfile(
            schema_id="assessment-profile",
            schema_version="1.0.0",
            profile_id="activation-test",
            version=SemVer(1, 0, 0),
            status="draft",
            items=(
                RequiredProfileItem(
                    capability_id="ec2.inventory",
                    capability_version="1.0.0",
                    required_fields=("instance_id", "account_id"),
                    target_scope="regional",
                    required_permissions=("ec2:DescribeInstances",),
                ),
            ),
            region_rule=RegionRule(mode="explicit", explicit_regions=("us-east-1",)),
            collection_window=CollectionWindow(period_type="monthly"),
            completeness_threshold=Decimal("1.0"),
        )

    def _make_invocation_request(self, profile_str: str, purpose: str) -> InvocationRequest:
        """Create an InvocationRequest in profile mode."""
        return InvocationRequest(
            schema_id="invocation-request",
            schema_version="1.0.0",
            profile=profile_str,
            targets=(AccountTarget(account_id="123456789012"),),
            regions=("us-east-1",),
            execution_context=ExecutionContext(
                caller_id="test-agent",
                correlation_id="corr-123",
                purpose=purpose,
            ),
        )

    def _make_registry_with_capability(self) -> CapabilityRegistryImpl:
        """Create a capability registry with the ec2.inventory capability registered."""
        from agentic.interfaces import Collector
        from agentic.models import CollectorOutcome

        class FakeEc2Collector:
            """Fake collector for testing."""

            def collect(self, *args, **kwargs) -> CollectorOutcome:
                return CollectorOutcome(status="succeeded", records=())

        registry = CapabilityRegistryImpl()
        descriptor = CapabilityDescriptor(
            capability_id="ec2.inventory",
            version=SemVer(1, 0, 0),
            permissions=("ec2:DescribeInstances",),
        )
        registry.register(descriptor, FakeEc2Collector())
        return registry

    def test_draft_profile_monthly_assessment_fails(self):
        """Draft profile with purpose=monthly-assessment returns failed status."""
        profile_registry = AssessmentProfileRegistryImpl()
        profile = self._make_simple_draft_profile()
        profile_registry.publish(profile)

        cap_registry = self._make_registry_with_capability()
        schema_processor = CanonicalSchemaProcessor()

        request = self._make_invocation_request(
            "activation-test@1.0.0", purpose="monthly-assessment"
        )

        result = invoke(
            request=request,
            registry=cap_registry,
            schema_processor=schema_processor,
            profile_registry=profile_registry,
        )

        assert result.execution_status == "failed", (
            "Draft profile must not be activated for monthly-assessment"
        )

    def test_draft_profile_empty_purpose_succeeds(self):
        """Draft profile with purpose='' succeeds if all capabilities registered."""
        profile_registry = AssessmentProfileRegistryImpl()
        profile = self._make_simple_draft_profile()
        profile_registry.publish(profile)

        cap_registry = self._make_registry_with_capability()
        schema_processor = CanonicalSchemaProcessor()

        request = self._make_invocation_request(
            "activation-test@1.0.0", purpose=""
        )

        result = invoke(
            request=request,
            registry=cap_registry,
            schema_processor=schema_processor,
            profile_registry=profile_registry,
        )

        assert result.execution_status == "succeeded", (
            "Draft profile with empty purpose should succeed when capabilities are registered"
        )

    def test_monthly_standard_draft_monthly_assessment_fails(self):
        """The actual monthly-standard@1.0.0 draft profile fails for monthly-assessment."""
        profile_registry = AssessmentProfileRegistryImpl()
        profile = create_monthly_standard_v1()
        profile_registry.publish(profile)

        cap_registry = CapabilityRegistryImpl()
        schema_processor = CanonicalSchemaProcessor()

        request = self._make_invocation_request(
            "monthly-standard@1.0.0", purpose="monthly-assessment"
        )

        result = invoke(
            request=request,
            registry=cap_registry,
            schema_processor=schema_processor,
            profile_registry=profile_registry,
        )

        assert result.execution_status == "failed"


# ---------------------------------------------------------------------------
# TestProfileSchemaRequirements (Req 3.6)
# ---------------------------------------------------------------------------


class TestProfileSchemaRequirements:
    """Tests for schema version metadata requirements."""

    def test_published_profile_has_schema_id(self):
        """Verify that published profile has schema_id set."""
        profile = create_monthly_standard_v1()
        assert profile.schema_id == "assessment-profile"

    def test_published_profile_has_schema_version(self):
        """Verify that published profile has schema_version set."""
        profile = create_monthly_standard_v1()
        assert profile.schema_version == "1.0.0"

    def test_assessment_profile_json_schema_exists(self):
        """Verify AssessmentProfile JSON Schema file exists at expected path."""
        schema_path = (
            Path(__file__).parent.parent
            / "agentic"
            / "schemas"
            / "assessment-profile"
            / "1.0.0.json"
        )
        assert schema_path.exists(), (
            f"Expected assessment-profile schema at {schema_path}"
        )

    def test_schema_id_and_version_consistent_with_schema_file(self):
        """Verify schema_id and version match what the JSON schema declares."""
        import json

        schema_path = (
            Path(__file__).parent.parent
            / "agentic"
            / "schemas"
            / "assessment-profile"
            / "1.0.0.json"
        )
        with open(schema_path) as f:
            schema = json.load(f)

        # The schema should declare schema_id as const "assessment-profile"
        assert schema["properties"]["schema_id"]["const"] == "assessment-profile"
        # The schema_version should match the pattern for semver
        assert "pattern" in schema["properties"]["schema_version"]

    def test_published_profile_schema_fields_nonempty(self):
        """Verify schema_id and schema_version are both non-empty strings."""
        profile = create_monthly_standard_v1()
        assert profile.schema_id != ""
        assert profile.schema_version != ""
        # Verify version is valid semver
        SemVer.parse(profile.schema_version)
