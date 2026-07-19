"""
Tests for Assessment Orchestrator — Profile Mode Integration.

Covers:
- Profile mode resolves capabilities from profile items (Req 5.2)
- Unsupported profile version returns failed InvocationResult
- Retired profile is rejected
- Draft profile with purpose="monthly-assessment" is rejected
- Draft profile with purpose="" (interactive use) is allowed
- Profile with empty items is rejected
- Result records profile_id, profile_version, manifest_version (Req 5.4)
- Explicit capability mode still works (no regression)
- Profile mode without profile_registry returns failed
- Invalid profile string format (no @) returns failed
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

import pytest

from agentic.models import (
    AccountTarget,
    AssessmentProfile,
    CapabilityDescriptor,
    CapabilityRequest,
    CollectionWindow,
    CollectorOutcome,
    ExecutionContext,
    InvocationRequest,
    InvocationResult,
    RegionRule,
    RequiredProfileItem,
    SemVer,
    StructuredError,
)
from agentic.orchestrator import invoke
from agentic.profile_registry import AssessmentProfileRegistryImpl
from agentic.registry import CapabilityRegistryImpl
from agentic.schemas.processor import CanonicalSchemaProcessor


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


class FakeCollector:
    """A minimal Collector implementation for testing."""

    def __init__(self, name: str = "fake"):
        self.name = name
        self.collect_called = False

    def collect(
        self,
        capability_id: str,
        capability_version: str,
        account_id: str,
        region_scope: str,
        parameters: Mapping[str, Any],
        session: Any,
    ) -> CollectorOutcome:
        self.collect_called = True
        return CollectorOutcome(status="succeeded", records=(), evidence=())


def _make_capability_registry() -> CapabilityRegistryImpl:
    """Create a registry with ec2.inventory and s3.inventory registered."""
    registry = CapabilityRegistryImpl()

    ec2_desc = CapabilityDescriptor(
        schema_id="capability-descriptor",
        schema_version="1.0.0",
        capability_id="ec2.inventory",
        version=SemVer(1, 0, 0),
        input_schema_ref="ec2-inventory-input/1.0.0",
        output_schema_ref="ec2-inventory-output/1.0.0",
        error_schema_ref="structured-error/1.0.0",
        permissions=("ec2:DescribeInstances",),
        allowed_operations=("ec2:DescribeInstances",),
        prerequisites=(),
        support_status="active",
    )
    registry.register(ec2_desc, FakeCollector("ec2"))

    s3_desc = CapabilityDescriptor(
        schema_id="capability-descriptor",
        schema_version="1.0.0",
        capability_id="s3.inventory",
        version=SemVer(1, 0, 0),
        input_schema_ref="s3-inventory-input/1.0.0",
        output_schema_ref="s3-inventory-output/1.0.0",
        error_schema_ref="structured-error/1.0.0",
        permissions=("s3:ListBuckets",),
        allowed_operations=("s3:ListBuckets",),
        prerequisites=(),
        support_status="active",
    )
    registry.register(s3_desc, FakeCollector("s3"))

    return registry


def _make_active_profile() -> AssessmentProfile:
    """Create an active profile with ec2 and s3 items."""
    return AssessmentProfile(
        schema_id="assessment-profile",
        schema_version="1.0.0",
        profile_id="monthly-standard",
        version=SemVer(1, 0, 0),
        status="active",
        items=(
            RequiredProfileItem(
                capability_id="ec2.inventory",
                capability_version="1.0.0",
                required_fields=("instance_id", "state"),
                target_scope="regional",
                required_permissions=("ec2:DescribeInstances",),
            ),
            RequiredProfileItem(
                capability_id="s3.inventory",
                capability_version="1.0.0",
                required_fields=("bucket_name",),
                target_scope="global",
                required_permissions=("s3:ListBuckets",),
            ),
        ),
        region_rule=RegionRule(mode="explicit", explicit_regions=("us-east-1",)),
        collection_window=CollectionWindow(period_type="monthly"),
        completeness_threshold=Decimal("1.0"),
        manifest_digest="test-manifest-digest",
    )


def _make_profile_registry_with_active() -> AssessmentProfileRegistryImpl:
    """Create a profile registry with an active monthly-standard profile."""
    profile_registry = AssessmentProfileRegistryImpl()
    profile = _make_active_profile()
    profile_registry.publish(profile)
    return profile_registry


def _make_profile_request(
    profile_str: str = "monthly-standard@1.0.0",
    purpose: str = "",
) -> InvocationRequest:
    """Create a valid profile-mode InvocationRequest."""
    return InvocationRequest(
        schema_id="invocation-request",
        schema_version="1.0.0",
        capabilities=None,
        profile=profile_str,
        targets=(AccountTarget(account_id="123456789012", role_ref=None),),
        regions=("us-east-1",),
        execution_context=ExecutionContext(
            caller_id="agent/test",
            correlation_id="corr-profile-001",
            idempotency_key=None,
            purpose=purpose,
            timeout_seconds=3600,
        ),
    )


def _make_explicit_capability_request() -> InvocationRequest:
    """Create a valid explicit capability mode request."""
    return InvocationRequest(
        schema_id="invocation-request",
        schema_version="1.0.0",
        capabilities=(
            CapabilityRequest(id="ec2.inventory", version="1.0.0", parameters={}),
        ),
        profile=None,
        targets=(AccountTarget(account_id="123456789012", role_ref=None),),
        regions=("ap-southeast-1",),
        execution_context=ExecutionContext(
            caller_id="agent/test",
            correlation_id="corr-explicit-001",
            idempotency_key=None,
            purpose="test",
            timeout_seconds=3600,
        ),
    )


# ---------------------------------------------------------------------------
# Profile Mode Tests
# ---------------------------------------------------------------------------


class TestProfileModeResolution:
    """Tests for profile mode integration in the orchestrator."""

    def test_profile_mode_resolves_capabilities_from_items(self):
        """Profile mode resolves capabilities from profile items (Req 5.2)."""
        registry = _make_capability_registry()
        profile_registry = _make_profile_registry_with_active()
        processor = CanonicalSchemaProcessor()

        request = _make_profile_request()
        result = invoke(request, registry, processor, profile_registry)

        assert isinstance(result, InvocationResult)
        assert result.execution_status == "succeeded"
        assert result.plan_digest != ""
        assert result.request_digest != ""

    def test_unsupported_profile_version_returns_failed(self):
        """Unsupported profile version returns failed InvocationResult."""
        registry = _make_capability_registry()
        profile_registry = _make_profile_registry_with_active()
        processor = CanonicalSchemaProcessor()

        request = _make_profile_request(profile_str="monthly-standard@9.9.9")
        result = invoke(request, registry, processor, profile_registry)

        assert isinstance(result, InvocationResult)
        assert result.execution_status == "failed"

    def test_unknown_profile_id_returns_failed(self):
        """Unknown profile ID returns failed InvocationResult."""
        registry = _make_capability_registry()
        profile_registry = _make_profile_registry_with_active()
        processor = CanonicalSchemaProcessor()

        request = _make_profile_request(profile_str="unknown-profile@1.0.0")
        result = invoke(request, registry, processor, profile_registry)

        assert isinstance(result, InvocationResult)
        assert result.execution_status == "failed"

    def test_retired_profile_is_rejected(self):
        """Retired profile is rejected with failed result."""
        registry = _make_capability_registry()
        profile_registry = AssessmentProfileRegistryImpl()
        processor = CanonicalSchemaProcessor()

        # Publish active first, then retire
        active_profile = _make_active_profile()
        profile_registry.publish(active_profile)

        retired_profile = AssessmentProfile(
            schema_id="assessment-profile",
            schema_version="1.0.0",
            profile_id="monthly-standard",
            version=SemVer(1, 1, 0),
            status="retired",
            items=(
                RequiredProfileItem(
                    capability_id="ec2.inventory",
                    capability_version="1.0.0",
                    required_fields=("instance_id", "state"),
                    target_scope="regional",
                    required_permissions=("ec2:DescribeInstances",),
                ),
                RequiredProfileItem(
                    capability_id="s3.inventory",
                    capability_version="1.0.0",
                    required_fields=("bucket_name",),
                    target_scope="global",
                    required_permissions=("s3:ListBuckets",),
                ),
            ),
            region_rule=RegionRule(mode="explicit", explicit_regions=("us-east-1",)),
            collection_window=CollectionWindow(period_type="monthly"),
            completeness_threshold=Decimal("1.0"),
            manifest_digest="test-manifest-digest",
        )
        profile_registry.publish(retired_profile)

        request = _make_profile_request(profile_str="monthly-standard@1.1.0")
        result = invoke(request, registry, processor, profile_registry)

        assert isinstance(result, InvocationResult)
        assert result.execution_status == "failed"

    def test_draft_profile_rejected_for_monthly_assessment(self):
        """Draft profile with purpose='monthly-assessment' is rejected."""
        registry = _make_capability_registry()
        profile_registry = AssessmentProfileRegistryImpl()
        processor = CanonicalSchemaProcessor()

        # Publish a draft profile
        draft_profile = AssessmentProfile(
            schema_id="assessment-profile",
            schema_version="1.0.0",
            profile_id="monthly-standard",
            version=SemVer(1, 0, 0),
            status="draft",
            items=(
                RequiredProfileItem(
                    capability_id="ec2.inventory",
                    capability_version="1.0.0",
                    required_fields=("instance_id",),
                    target_scope="regional",
                    required_permissions=("ec2:DescribeInstances",),
                ),
            ),
            region_rule=RegionRule(mode="explicit", explicit_regions=("us-east-1",)),
            collection_window=CollectionWindow(period_type="monthly"),
            completeness_threshold=Decimal("1.0"),
            manifest_digest="test-manifest-digest",
        )
        profile_registry.publish(draft_profile)

        request = _make_profile_request(
            profile_str="monthly-standard@1.0.0",
            purpose="monthly-assessment",
        )
        result = invoke(request, registry, processor, profile_registry)

        assert isinstance(result, InvocationResult)
        assert result.execution_status == "failed"

    def test_draft_profile_allowed_for_interactive_use(self):
        """Draft profile with purpose='' (interactive use) is allowed."""
        registry = _make_capability_registry()
        profile_registry = AssessmentProfileRegistryImpl()
        processor = CanonicalSchemaProcessor()

        # Publish a draft profile
        draft_profile = AssessmentProfile(
            schema_id="assessment-profile",
            schema_version="1.0.0",
            profile_id="monthly-standard",
            version=SemVer(1, 0, 0),
            status="draft",
            items=(
                RequiredProfileItem(
                    capability_id="ec2.inventory",
                    capability_version="1.0.0",
                    required_fields=("instance_id",),
                    target_scope="regional",
                    required_permissions=("ec2:DescribeInstances",),
                ),
            ),
            region_rule=RegionRule(mode="explicit", explicit_regions=("us-east-1",)),
            collection_window=CollectionWindow(period_type="monthly"),
            completeness_threshold=Decimal("1.0"),
            manifest_digest="test-manifest-digest",
        )
        profile_registry.publish(draft_profile)

        request = _make_profile_request(
            profile_str="monthly-standard@1.0.0",
            purpose="",  # Interactive/agent invocation
        )
        result = invoke(request, registry, processor, profile_registry)

        assert isinstance(result, InvocationResult)
        assert result.execution_status == "succeeded"

    def test_profile_with_empty_items_is_rejected(self):
        """Profile with empty items is rejected."""
        registry = _make_capability_registry()
        profile_registry = AssessmentProfileRegistryImpl()
        processor = CanonicalSchemaProcessor()

        # We need to bypass publish validation for this test.
        # Manually insert a profile with empty items into the registry.
        empty_profile = AssessmentProfile(
            schema_id="assessment-profile",
            schema_version="1.0.0",
            profile_id="empty-profile",
            version=SemVer(1, 0, 0),
            status="active",
            items=(),  # No items
            region_rule=RegionRule(mode="explicit", explicit_regions=("us-east-1",)),
            collection_window=CollectionWindow(period_type="monthly"),
            completeness_threshold=Decimal("1.0"),
            manifest_digest="test-manifest-digest",
        )
        # Manually insert (bypassing publish validation which rejects empty items)
        digest = profile_registry._compute_content_digest(empty_profile)
        profile_registry._profiles["empty-profile"] = {
            "1.0.0": (empty_profile, digest)
        }

        request = _make_profile_request(profile_str="empty-profile@1.0.0")
        result = invoke(request, registry, processor, profile_registry)

        assert isinstance(result, InvocationResult)
        assert result.execution_status == "failed"

    def test_result_records_profile_identifiers(self):
        """Result records profile_id, profile_version, manifest_version (Req 5.4)."""
        registry = _make_capability_registry()
        profile_registry = _make_profile_registry_with_active()
        processor = CanonicalSchemaProcessor()

        request = _make_profile_request()
        result = invoke(request, registry, processor, profile_registry)

        assert result.execution_status == "succeeded"
        assert result.profile_id == "monthly-standard"
        assert result.profile_version == "1.0.0"
        assert result.manifest_version != ""

    def test_profile_mode_without_registry_returns_failed(self):
        """Profile mode without profile_registry parameter returns failed."""
        registry = _make_capability_registry()
        processor = CanonicalSchemaProcessor()

        request = _make_profile_request()
        # No profile_registry provided
        result = invoke(request, registry, processor, profile_registry=None)

        assert isinstance(result, InvocationResult)
        assert result.execution_status == "failed"

    def test_invalid_profile_string_format_returns_failed(self):
        """Profile string without '@' separator returns failed."""
        registry = _make_capability_registry()
        profile_registry = _make_profile_registry_with_active()
        processor = CanonicalSchemaProcessor()

        request = _make_profile_request(profile_str="monthly-standard-no-version")
        result = invoke(request, registry, processor, profile_registry)

        assert isinstance(result, InvocationResult)
        assert result.execution_status == "failed"


# ---------------------------------------------------------------------------
# Explicit Capability Mode (No Regression)
# ---------------------------------------------------------------------------


class TestExplicitModeNoRegression:
    """Ensure explicit capability mode still works correctly."""

    def test_explicit_capability_mode_succeeds(self):
        """Explicit capability mode still works with profile_registry param."""
        registry = _make_capability_registry()
        profile_registry = _make_profile_registry_with_active()
        processor = CanonicalSchemaProcessor()

        request = _make_explicit_capability_request()
        result = invoke(request, registry, processor, profile_registry)

        assert isinstance(result, InvocationResult)
        assert result.execution_status == "succeeded"
        assert result.plan_digest != ""
        assert result.request_digest != ""
        # No profile info in explicit mode
        assert result.profile_id is None
        assert result.profile_version is None

    def test_explicit_capability_mode_without_profile_registry(self):
        """Explicit mode works even when no profile_registry is provided."""
        registry = _make_capability_registry()
        processor = CanonicalSchemaProcessor()

        request = _make_explicit_capability_request()
        result = invoke(request, registry, processor)

        assert isinstance(result, InvocationResult)
        assert result.execution_status == "succeeded"
        assert result.plan_digest != ""

    def test_explicit_mode_unsupported_capability_still_fails(self):
        """Explicit mode still rejects unsupported capabilities."""
        registry = _make_capability_registry()
        processor = CanonicalSchemaProcessor()

        request = InvocationRequest(
            schema_id="invocation-request",
            schema_version="1.0.0",
            capabilities=(
                CapabilityRequest(id="unknown.cap", version="1.0.0", parameters={}),
            ),
            profile=None,
            targets=(AccountTarget(account_id="123456789012"),),
            regions=("us-east-1",),
            execution_context=ExecutionContext(
                caller_id="agent/test",
                correlation_id="corr-explicit-fail",
            ),
        )
        result = invoke(request, registry, processor)

        assert result.execution_status == "failed"
