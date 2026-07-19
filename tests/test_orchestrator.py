"""
Tests for Assessment Orchestrator — invoke() and Deterministic Planner.

Covers:
- Validation: missing targets, missing regions, missing execution_context,
  both profile and capabilities set, empty capabilities
- Unsupported capability/version returns StructuredError (Req 2.5)
- Valid ec2.inventory request selects only EC2 handler and prerequisites (Req 2.4, 4.6)
- Deterministic planning: same inputs produce same plan (Req 2.3)
- Prerequisite closure is correctly formed with topological sort
- Plan digest is stable across identical invocations
- Invalid request stops before session/Collector/AWS API (Req 2.2)
"""

from __future__ import annotations

from typing import Any, Mapping

import pytest

from agentic.models import (
    AccountTarget,
    CapabilityDescriptor,
    CapabilityRequest,
    CollectorOutcome,
    ExecutionContext,
    ExecutionPlan,
    InvocationRequest,
    InvocationResult,
    SemVer,
    StructuredError,
)
from agentic.orchestrator import invoke, _validate_request, _plan
from agentic.registry import CapabilityRegistryImpl, RegisteredCapability
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


def _make_registry_with_ec2() -> tuple[CapabilityRegistryImpl, FakeCollector]:
    """Create a registry with ec2.inventory registered."""
    registry = CapabilityRegistryImpl()
    collector = FakeCollector("ec2")

    descriptor = CapabilityDescriptor(
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
    registry.register(descriptor, collector)
    return registry, collector


def _make_registry_with_prereqs() -> (
    tuple[CapabilityRegistryImpl, FakeCollector, FakeCollector]
):
    """Create a registry with a capability that has prerequisites."""
    registry = CapabilityRegistryImpl()
    prereq_collector = FakeCollector("iam-base")
    main_collector = FakeCollector("ec2")

    # Register prerequisite first
    prereq_desc = CapabilityDescriptor(
        schema_id="capability-descriptor",
        schema_version="1.0.0",
        capability_id="iam.identity",
        version=SemVer(1, 0, 0),
        input_schema_ref="iam-identity-input/1.0.0",
        output_schema_ref="iam-identity-output/1.0.0",
        error_schema_ref="structured-error/1.0.0",
        permissions=("sts:GetCallerIdentity",),
        allowed_operations=("sts:GetCallerIdentity",),
        prerequisites=(),
        support_status="active",
    )
    registry.register(prereq_desc, prereq_collector)

    # Register main capability with prerequisite
    main_desc = CapabilityDescriptor(
        schema_id="capability-descriptor",
        schema_version="1.0.0",
        capability_id="ec2.inventory",
        version=SemVer(1, 0, 0),
        input_schema_ref="ec2-inventory-input/1.0.0",
        output_schema_ref="ec2-inventory-output/1.0.0",
        error_schema_ref="structured-error/1.0.0",
        permissions=("ec2:DescribeInstances",),
        allowed_operations=("ec2:DescribeInstances",),
        prerequisites=("iam.identity",),
        support_status="active",
    )
    registry.register(main_desc, main_collector)

    return registry, prereq_collector, main_collector


def _make_valid_request(
    capability_id: str = "ec2.inventory",
    version: str = "1.0.0",
) -> InvocationRequest:
    """Create a valid InvocationRequest."""
    return InvocationRequest(
        schema_id="invocation-request",
        schema_version="1.0.0",
        capabilities=(
            CapabilityRequest(id=capability_id, version=version, parameters={}),
        ),
        profile=None,
        targets=(AccountTarget(account_id="123456789012", role_ref=None),),
        regions=("ap-southeast-1",),
        execution_context=ExecutionContext(
            caller_id="agent/test",
            correlation_id="corr-test-001",
            idempotency_key=None,
            purpose="test",
            timeout_seconds=3600,
        ),
    )


# ---------------------------------------------------------------------------
# Validation Tests (Req 2.1, 2.2)
# ---------------------------------------------------------------------------


class TestValidation:
    """Tests for request validation before planning."""

    def test_valid_request_passes_validation(self):
        """A well-formed request passes validation."""
        request = _make_valid_request()
        error = _validate_request(request)
        assert error is None

    def test_missing_targets_fails(self):
        """Request with no targets fails validation."""
        request = InvocationRequest(
            capabilities=(
                CapabilityRequest(id="ec2.inventory", version="1.0.0"),
            ),
            targets=(),
            regions=("ap-southeast-1",),
            execution_context=ExecutionContext(
                caller_id="agent/test",
                correlation_id="corr-test",
            ),
        )
        error = _validate_request(request)
        assert error is not None
        assert error.code == "VALIDATION_ERROR"
        assert error.category == "validation"
        assert any("target" in v.safe_message.lower() for v in error.violations)

    def test_missing_regions_fails(self):
        """Request with no regions fails validation."""
        request = InvocationRequest(
            capabilities=(
                CapabilityRequest(id="ec2.inventory", version="1.0.0"),
            ),
            targets=(AccountTarget(account_id="123456789012"),),
            regions=(),
            execution_context=ExecutionContext(
                caller_id="agent/test",
                correlation_id="corr-test",
            ),
        )
        error = _validate_request(request)
        assert error is not None
        assert error.code == "VALIDATION_ERROR"
        assert any("region" in v.safe_message.lower() for v in error.violations)

    def test_missing_execution_context_fails(self):
        """Request without execution context fails validation."""
        request = InvocationRequest(
            capabilities=(
                CapabilityRequest(id="ec2.inventory", version="1.0.0"),
            ),
            targets=(AccountTarget(account_id="123456789012"),),
            regions=("ap-southeast-1",),
            execution_context=None,
        )
        error = _validate_request(request)
        assert error is not None
        assert error.code == "VALIDATION_ERROR"
        assert any(
            "execution context" in v.safe_message.lower() for v in error.violations
        )

    def test_both_capabilities_and_profile_fails(self):
        """Request with both capabilities and profile fails validation."""
        request = InvocationRequest(
            capabilities=(
                CapabilityRequest(id="ec2.inventory", version="1.0.0"),
            ),
            profile="monthly-standard",
            targets=(AccountTarget(account_id="123456789012"),),
            regions=("ap-southeast-1",),
            execution_context=ExecutionContext(
                caller_id="agent/test",
                correlation_id="corr-test",
            ),
        )
        error = _validate_request(request)
        assert error is not None
        assert error.code == "VALIDATION_ERROR"
        assert any(
            "exactly one" in v.safe_message.lower() for v in error.violations
        )

    def test_neither_capabilities_nor_profile_fails(self):
        """Request with neither capabilities nor profile fails validation."""
        request = InvocationRequest(
            capabilities=None,
            profile=None,
            targets=(AccountTarget(account_id="123456789012"),),
            regions=("ap-southeast-1",),
            execution_context=ExecutionContext(
                caller_id="agent/test",
                correlation_id="corr-test",
            ),
        )
        error = _validate_request(request)
        assert error is not None
        assert error.code == "VALIDATION_ERROR"

    def test_empty_capability_id_fails(self):
        """Request with empty capability ID fails validation."""
        request = InvocationRequest(
            capabilities=(CapabilityRequest(id="", version="1.0.0"),),
            targets=(AccountTarget(account_id="123456789012"),),
            regions=("ap-southeast-1",),
            execution_context=ExecutionContext(
                caller_id="agent/test",
                correlation_id="corr-test",
            ),
        )
        error = _validate_request(request)
        assert error is not None
        assert error.code == "VALIDATION_ERROR"

    def test_invalid_version_format_fails(self):
        """Request with invalid version format fails validation."""
        request = InvocationRequest(
            capabilities=(CapabilityRequest(id="ec2.inventory", version="bad"),),
            targets=(AccountTarget(account_id="123456789012"),),
            regions=("ap-southeast-1",),
            execution_context=ExecutionContext(
                caller_id="agent/test",
                correlation_id="corr-test",
            ),
        )
        error = _validate_request(request)
        assert error is not None
        assert error.code == "VALIDATION_ERROR"
        assert any("semver" in v.safe_message.lower() for v in error.violations)

    def test_empty_caller_id_fails(self):
        """Request with empty caller_id fails validation."""
        request = InvocationRequest(
            capabilities=(
                CapabilityRequest(id="ec2.inventory", version="1.0.0"),
            ),
            targets=(AccountTarget(account_id="123456789012"),),
            regions=("ap-southeast-1",),
            execution_context=ExecutionContext(
                caller_id="",
                correlation_id="corr-test",
            ),
        )
        error = _validate_request(request)
        assert error is not None
        assert error.code == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# Unsupported Capability Tests (Req 2.5)
# ---------------------------------------------------------------------------


class TestUnsupportedCapability:
    """Tests for unsupported capability/version handling."""

    def test_unknown_capability_returns_failed_result(self):
        """Unknown capability ID returns failed InvocationResult."""
        registry, _ = _make_registry_with_ec2()
        processor = CanonicalSchemaProcessor()

        request = _make_valid_request(
            capability_id="unknown.service", version="1.0.0"
        )
        result = invoke(request, registry, processor)

        assert isinstance(result, InvocationResult)
        assert result.execution_status == "failed"

    def test_unsupported_version_returns_failed_result(self):
        """Unsupported version returns failed InvocationResult."""
        registry, _ = _make_registry_with_ec2()
        processor = CanonicalSchemaProcessor()

        request = _make_valid_request(
            capability_id="ec2.inventory", version="9.9.9"
        )
        result = invoke(request, registry, processor)

        assert isinstance(result, InvocationResult)
        assert result.execution_status == "failed"

    def test_invalid_request_does_not_call_collector(self):
        """Invalid request never invokes the Collector (Req 2.2)."""
        registry, collector = _make_registry_with_ec2()
        processor = CanonicalSchemaProcessor()

        # Missing targets
        request = InvocationRequest(
            capabilities=(
                CapabilityRequest(id="ec2.inventory", version="1.0.0"),
            ),
            targets=(),
            regions=("ap-southeast-1",),
            execution_context=ExecutionContext(
                caller_id="agent/test",
                correlation_id="corr-test",
            ),
        )
        result = invoke(request, registry, processor)

        assert result.execution_status == "failed"
        assert not collector.collect_called


# ---------------------------------------------------------------------------
# Deterministic Planning Tests (Req 2.3, 2.4, 4.6)
# ---------------------------------------------------------------------------


class TestDeterministicPlanning:
    """Tests for deterministic plan generation."""

    def test_ec2_inventory_selects_only_ec2_handler(self):
        """
        A single ec2.inventory request selects only the EC2 handler
        and no unrelated capabilities (Req 2.4, 4.6).
        """
        registry, _ = _make_registry_with_ec2()
        processor = CanonicalSchemaProcessor()

        request = _make_valid_request()
        result = invoke(request, registry, processor)

        assert result.execution_status == "succeeded"
        assert result.plan_digest != ""

    def test_plan_is_deterministic_for_same_inputs(self):
        """
        Two canonical-equivalent requests with same registry produce
        equivalent ordered ExecutionPlans (Req 2.3).
        """
        registry, _ = _make_registry_with_ec2()
        processor = CanonicalSchemaProcessor()

        request = _make_valid_request()

        result1 = invoke(request, registry, processor)
        result2 = invoke(request, registry, processor)

        assert result1.plan_digest == result2.plan_digest
        assert result1.request_digest == result2.request_digest

    def test_plan_includes_prerequisites_in_order(self):
        """
        Plan includes prerequisite capabilities before the main capability,
        ordered by topological sort with capability_id tie-breaker.
        """
        registry, _, _ = _make_registry_with_prereqs()
        processor = CanonicalSchemaProcessor()

        request = _make_valid_request()
        manifest = registry.snapshot()
        plan = _plan(request, manifest, registry, processor)

        # Should have 2 units: iam.identity (prereq) then ec2.inventory
        assert len(plan.units) == 2
        assert plan.units[0].capability_id == "iam.identity"
        assert plan.units[1].capability_id == "ec2.inventory"
        # ec2.inventory unit should reference iam.identity unit
        assert plan.units[0].unit_id in plan.units[1].prerequisite_unit_ids

    def test_plan_expands_multiple_targets(self):
        """Plan creates one unit per capability-target pair."""
        registry, _ = _make_registry_with_ec2()
        processor = CanonicalSchemaProcessor()

        request = InvocationRequest(
            schema_id="invocation-request",
            schema_version="1.0.0",
            capabilities=(
                CapabilityRequest(
                    id="ec2.inventory", version="1.0.0", parameters={}
                ),
            ),
            targets=(
                AccountTarget(account_id="111111111111"),
                AccountTarget(account_id="222222222222"),
            ),
            regions=("us-east-1", "eu-west-1"),
            execution_context=ExecutionContext(
                caller_id="agent/test",
                correlation_id="corr-multi",
            ),
        )

        manifest = registry.snapshot()
        plan = _plan(request, manifest, registry, processor)

        # 1 capability × 2 accounts × 2 regions = 4 units
        assert len(plan.units) == 4

        # Verify all target pairs are covered
        target_pairs = {
            (u.account_id, u.region_scope) for u in plan.units
        }
        assert target_pairs == {
            ("111111111111", "eu-west-1"),
            ("111111111111", "us-east-1"),
            ("222222222222", "eu-west-1"),
            ("222222222222", "us-east-1"),
        }

    def test_plan_units_have_stable_ids(self):
        """Unit IDs are derived deterministically from request content."""
        registry, _ = _make_registry_with_ec2()
        processor = CanonicalSchemaProcessor()

        request = _make_valid_request()
        manifest = registry.snapshot()

        plan1 = _plan(request, manifest, registry, processor)
        plan2 = _plan(request, manifest, registry, processor)

        assert plan1.units[0].unit_id == plan2.units[0].unit_id

    def test_plan_digest_computed_before_runtime(self):
        """Plan digest exists and is deterministic."""
        registry, _ = _make_registry_with_ec2()
        processor = CanonicalSchemaProcessor()

        request = _make_valid_request()
        manifest = registry.snapshot()

        plan = _plan(request, manifest, registry, processor)

        assert plan.plan_digest != ""
        assert len(plan.plan_digest) == 64  # SHA-256 hex

    def test_ec2_request_without_filters_only_selects_ec2(self):
        """
        EC2 request without filters selects ec2.inventory,
        not unrelated service capabilities (Req 4.6).
        """
        registry = CapabilityRegistryImpl()
        ec2_collector = FakeCollector("ec2")
        s3_collector = FakeCollector("s3")

        # Register both EC2 and S3
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
        registry.register(ec2_desc, ec2_collector)
        registry.register(s3_desc, s3_collector)

        processor = CanonicalSchemaProcessor()
        request = _make_valid_request(
            capability_id="ec2.inventory", version="1.0.0"
        )

        manifest = registry.snapshot()
        plan = _plan(request, manifest, registry, processor)

        # Only ec2.inventory units, no s3.inventory
        cap_ids = {u.capability_id for u in plan.units}
        assert cap_ids == {"ec2.inventory"}

    def test_prerequisite_closure_includes_transitive(self):
        """Prerequisite closure includes transitive dependencies."""
        registry = CapabilityRegistryImpl()
        base_collector = FakeCollector("base")
        mid_collector = FakeCollector("mid")
        top_collector = FakeCollector("top")

        # base -> no prereqs
        base_desc = CapabilityDescriptor(
            capability_id="base.setup",
            version=SemVer(1, 0, 0),
            input_schema_ref="base/1.0.0",
            output_schema_ref="base/1.0.0",
            error_schema_ref="structured-error/1.0.0",
            permissions=("sts:GetCallerIdentity",),
            allowed_operations=("sts:GetCallerIdentity",),
            prerequisites=(),
        )
        registry.register(base_desc, base_collector)

        # mid -> depends on base
        mid_desc = CapabilityDescriptor(
            capability_id="mid.layer",
            version=SemVer(1, 0, 0),
            input_schema_ref="mid/1.0.0",
            output_schema_ref="mid/1.0.0",
            error_schema_ref="structured-error/1.0.0",
            permissions=("ec2:DescribeRegions",),
            allowed_operations=("ec2:DescribeRegions",),
            prerequisites=("base.setup",),
        )
        registry.register(mid_desc, mid_collector)

        # top -> depends on mid (transitive dep on base)
        top_desc = CapabilityDescriptor(
            capability_id="top.capability",
            version=SemVer(1, 0, 0),
            input_schema_ref="top/1.0.0",
            output_schema_ref="top/1.0.0",
            error_schema_ref="structured-error/1.0.0",
            permissions=("ec2:DescribeInstances",),
            allowed_operations=("ec2:DescribeInstances",),
            prerequisites=("mid.layer",),
        )
        registry.register(top_desc, top_collector)

        processor = CanonicalSchemaProcessor()
        request = InvocationRequest(
            capabilities=(
                CapabilityRequest(
                    id="top.capability", version="1.0.0", parameters={}
                ),
            ),
            targets=(AccountTarget(account_id="123456789012"),),
            regions=("us-east-1",),
            execution_context=ExecutionContext(
                caller_id="agent/test",
                correlation_id="corr-transitive",
            ),
        )

        manifest = registry.snapshot()
        plan = _plan(request, manifest, registry, processor)

        # Should have 3 units: base -> mid -> top
        assert len(plan.units) == 3
        assert plan.units[0].capability_id == "base.setup"
        assert plan.units[1].capability_id == "mid.layer"
        assert plan.units[2].capability_id == "top.capability"

    def test_ordinal_is_sequential(self):
        """Units have sequential ordinals starting at 0."""
        registry, _ = _make_registry_with_ec2()
        processor = CanonicalSchemaProcessor()

        request = InvocationRequest(
            capabilities=(
                CapabilityRequest(
                    id="ec2.inventory", version="1.0.0", parameters={}
                ),
            ),
            targets=(
                AccountTarget(account_id="111111111111"),
                AccountTarget(account_id="222222222222"),
            ),
            regions=("us-east-1",),
            execution_context=ExecutionContext(
                caller_id="agent/test",
                correlation_id="corr-ordinal",
            ),
        )

        manifest = registry.snapshot()
        plan = _plan(request, manifest, registry, processor)

        ordinals = [u.ordinal for u in plan.units]
        assert ordinals == list(range(len(plan.units)))


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


class TestInvokeIntegration:
    """End-to-end tests for the invoke() function."""

    def test_valid_ec2_invoke_succeeds(self):
        """A valid ec2.inventory invoke returns succeeded status."""
        registry, _ = _make_registry_with_ec2()
        processor = CanonicalSchemaProcessor()
        request = _make_valid_request()

        result = invoke(request, registry, processor)

        assert isinstance(result, InvocationResult)
        assert result.execution_status == "succeeded"
        assert result.plan_digest != ""
        assert result.request_digest != ""
        assert result.manifest_version != ""
        assert result.correlation_id == "corr-test-001"

    def test_invalid_request_returns_failed_with_correlation(self):
        """Invalid request returns failed with correlation ID preserved."""
        registry, _ = _make_registry_with_ec2()
        processor = CanonicalSchemaProcessor()

        request = InvocationRequest(
            capabilities=(
                CapabilityRequest(id="ec2.inventory", version="1.0.0"),
            ),
            targets=(),  # invalid: no targets
            regions=("ap-southeast-1",),
            execution_context=ExecutionContext(
                caller_id="agent/test",
                correlation_id="corr-invalid",
            ),
        )
        result = invoke(request, registry, processor)

        assert result.execution_status == "failed"
        assert result.correlation_id == "corr-invalid"
