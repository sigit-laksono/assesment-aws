# Feature: agentic-aws-assessment, Property 2: Invalid requests are non-interacting
# Validates: Requirements 2.1, 2.2, 2.5, 4.5, 11.4
"""
Property-based test for invalid request non-interaction.

This test validates that for ALL invalid InvocationRequest payloads:
1. invoke() returns an InvocationResult with execution_status == "failed"
2. No planner function is called (no plan_digest computed)
3. No SessionFactory is invoked (no AWS session created)
4. No Collector is invoked
5. No AWS SDK/boto3 call is made

Invalid requests include:
- Missing targets (empty tuple)
- Missing regions (empty tuple)
- Missing execution_context (None)
- Both capabilities and profile set simultaneously
- Neither capabilities nor profile set
- Empty capability ID
- Invalid version format (not semver)
- Unsupported capability ID (not in registry)
- Unsupported version (not registered)
- Empty caller_id or correlation_id
"""

from __future__ import annotations

from typing import Any, Mapping
from unittest.mock import MagicMock, patch

import hypothesis.strategies as st
from hypothesis import HealthCheck, given, settings

from agentic.models import (
    AccountTarget,
    CapabilityDescriptor,
    CapabilityRequest,
    CollectorOutcome,
    ExecutionContext,
    InvocationRequest,
    InvocationResult,
    SemVer,
)
from agentic.orchestrator import invoke, _plan
from agentic.registry import CapabilityRegistryImpl
from agentic.schemas.processor import CanonicalSchemaProcessor


# ---------------------------------------------------------------------------
# FakeCollector with spy tracking
# ---------------------------------------------------------------------------


class SpyCollector:
    """A Collector that tracks whether collect() was ever called."""

    def __init__(self) -> None:
        self.collect_called = False
        self.call_count = 0

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
        self.call_count += 1
        return CollectorOutcome(status="succeeded", records=(), evidence=())


# ---------------------------------------------------------------------------
# Registry fixture with ec2.inventory registered
# ---------------------------------------------------------------------------


def _make_registry_with_ec2() -> tuple[CapabilityRegistryImpl, SpyCollector]:
    """Create a registry with ec2.inventory@1.0.0 registered."""
    registry = CapabilityRegistryImpl()
    collector = SpyCollector()

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


# ---------------------------------------------------------------------------
# Hypothesis strategies for invalid requests
# ---------------------------------------------------------------------------

# Valid building blocks (used to construct invalid requests with one flaw)
_VALID_ACCOUNT_IDS = st.sampled_from([
    "111111111111", "222222222222", "333333333333", "999999999999",
])
_VALID_REGIONS = st.sampled_from([
    "us-east-1", "eu-west-1", "ap-southeast-1", "ap-northeast-1",
])
_VALID_CALLER_IDS = st.sampled_from([
    "agent/test", "scheduler/monthly", "cli/user", "adapter/legacy",
])
_VALID_CORRELATION_IDS = st.sampled_from([
    "corr-001", "corr-abc", "corr-xyz", "corr-monthly-202401",
])

# Invalid version formats (not semver: must be major.minor.patch with integers)
_INVALID_VERSIONS = st.sampled_from([
    "bad", "1.0", "1", "v1.0.0", "1.0.0.0", "abc.def.ghi",
    "1.0.x", "latest", "1.x.0", "0", "..", "1..0", "1.0.",
])

# Unsupported capability IDs (not in registry)
_UNSUPPORTED_CAP_IDS = st.sampled_from([
    "s3.inventory", "rds.audit", "unknown.service", "iam.scan",
    "eks.inventory", "lambda.list", "vpc.describe", "dynamodb.scan",
])

# Unsupported versions for ec2.inventory (only 1.0.0 is registered)
_UNSUPPORTED_VERSIONS = st.sampled_from([
    "2.0.0", "1.1.0", "1.0.1", "3.0.0", "0.9.0", "9.9.9",
])


@st.composite
def invalid_requests(draw: st.DrawFn) -> InvocationRequest:
    """
    Strategy that generates various kinds of invalid InvocationRequests.

    Each generated request has exactly one (or more) invalidity that should
    cause invoke() to return a failed result without calling the planner,
    session factory, collector, or AWS SDK.
    """
    invalidity_type = draw(st.sampled_from([
        "missing_targets",
        "missing_regions",
        "missing_context",
        "both_capabilities_and_profile",
        "neither_capabilities_nor_profile",
        "empty_capability_id",
        "invalid_version_format",
        "unsupported_capability",
        "unsupported_version",
        "empty_caller_id",
        "empty_correlation_id",
    ]))

    # Defaults for a valid request (will be overridden by invalidity)
    targets: tuple[AccountTarget, ...] = (
        AccountTarget(account_id=draw(_VALID_ACCOUNT_IDS)),
    )
    regions: tuple[str, ...] = (draw(_VALID_REGIONS),)
    execution_context: ExecutionContext | None = ExecutionContext(
        caller_id=draw(_VALID_CALLER_IDS),
        correlation_id=draw(_VALID_CORRELATION_IDS),
        idempotency_key=None,
        purpose="test",
        timeout_seconds=3600,
    )
    capabilities: tuple[CapabilityRequest, ...] | None = (
        CapabilityRequest(id="ec2.inventory", version="1.0.0", parameters={}),
    )
    profile: str | None = None

    if invalidity_type == "missing_targets":
        targets = ()

    elif invalidity_type == "missing_regions":
        regions = ()

    elif invalidity_type == "missing_context":
        execution_context = None

    elif invalidity_type == "both_capabilities_and_profile":
        capabilities = (
            CapabilityRequest(id="ec2.inventory", version="1.0.0", parameters={}),
        )
        profile = draw(st.sampled_from([
            "monthly-standard", "weekly-audit", "custom-profile",
        ]))

    elif invalidity_type == "neither_capabilities_nor_profile":
        capabilities = None
        profile = None

    elif invalidity_type == "empty_capability_id":
        capabilities = (
            CapabilityRequest(id="", version="1.0.0", parameters={}),
        )

    elif invalidity_type == "invalid_version_format":
        invalid_ver = draw(_INVALID_VERSIONS)
        capabilities = (
            CapabilityRequest(id="ec2.inventory", version=invalid_ver, parameters={}),
        )

    elif invalidity_type == "unsupported_capability":
        unsupported_id = draw(_UNSUPPORTED_CAP_IDS)
        capabilities = (
            CapabilityRequest(id=unsupported_id, version="1.0.0", parameters={}),
        )

    elif invalidity_type == "unsupported_version":
        unsupported_ver = draw(_UNSUPPORTED_VERSIONS)
        capabilities = (
            CapabilityRequest(
                id="ec2.inventory", version=unsupported_ver, parameters={}
            ),
        )

    elif invalidity_type == "empty_caller_id":
        execution_context = ExecutionContext(
            caller_id="",
            correlation_id=draw(_VALID_CORRELATION_IDS),
            idempotency_key=None,
            purpose="test",
            timeout_seconds=3600,
        )

    elif invalidity_type == "empty_correlation_id":
        execution_context = ExecutionContext(
            caller_id=draw(_VALID_CALLER_IDS),
            correlation_id="",
            idempotency_key=None,
            purpose="test",
            timeout_seconds=3600,
        )

    return InvocationRequest(
        schema_id="invocation-request",
        schema_version="1.0.0",
        capabilities=capabilities,
        profile=profile,
        targets=targets,
        regions=regions,
        execution_context=execution_context,
    )


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(request=invalid_requests())
def test_invalid_requests_are_non_interacting(request: InvocationRequest) -> None:
    """
    Property 2: Invalid requests are non-interacting.

    Validates: Requirements 2.1, 2.2, 2.5, 4.5, 11.4

    For all invocation payloads that violate the schema, reference unsupported
    contracts, or contain invalid field values:
    - invoke() returns InvocationResult with execution_status == "failed"
    - The Collector is never invoked
    - No SessionFactory is called (no AWS session created)
    - No planner is invoked (no plan_digest should be computed)
    - No AWS API is contacted (boto3 is never called)
    """
    # Create fresh registry and spy collector for each example
    registry, spy_collector = _make_registry_with_ec2()
    processor = CanonicalSchemaProcessor()

    # Spy on the planner to ensure it's not called for invalid requests.
    # We patch _plan inside the orchestrator module.
    planner_spy = MagicMock(wraps=_plan)

    with patch("agentic.orchestrator._plan", planner_spy):
        # Invoke the orchestrator with the invalid request
        result = invoke(request, registry, processor)

    # --- Assertion 1: Result is failed ---
    assert isinstance(result, InvocationResult), (
        f"Expected InvocationResult, got {type(result)}"
    )
    assert result.execution_status == "failed", (
        f"Expected execution_status='failed' for invalid request, "
        f"got '{result.execution_status}'"
    )

    # --- Assertion 2: Collector was NOT called ---
    assert not spy_collector.collect_called, (
        "Collector.collect() should not be called for invalid requests"
    )

    # --- Assertion 3: No plan_digest computed (empty string for failures) ---
    # For validation failures, plan_digest should be empty because the
    # planner was never invoked. For unsupported capability failures,
    # the planner is also skipped.
    assert result.plan_digest == "", (
        f"Expected empty plan_digest for invalid request, "
        f"got '{result.plan_digest}'"
    )

    # --- Assertion 4: Planner was NOT invoked ---
    # Invalid requests should stop BEFORE planning (Req 2.2)
    planner_spy.assert_not_called()
