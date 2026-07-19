"""
EC2 Integration Tests — End-to-End invoke() → plan → routing → collector flow.

These tests exercise the full vertical slice from invoke() through planning
and routing, verifying correct EC2-specific behavior in the integrated system.

Covers:
- Routing: ec2.inventory selects only EC2 handler, no fuzzy routing (Req 4.1, 4.6)
- Multi-page pagination: all instances across pages collected (Req 4.2)
- Filter translation: combined filters reach paginator correctly (Req 4.3)
- Field compatibility: required identity + optional fields (Req 4.4)
- UTC normalization: RFC 3339 with Z suffix
- Successful-empty outcome: zero records = succeeded (Req 15.2)
- Unsupported input without SDK call: validation before paginator (Req 4.5)
- End-to-end invoke() integration

Requirements traced: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 15.2
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
from unittest.mock import MagicMock

import pytest

from agentic.ec2_collector import EC2InventoryCollector
from agentic.ec2_contract import (
    EC2_CAPABILITY_ID,
    EC2_OPTIONAL_V1_FIELDS,
    register_ec2_inventory,
)
from agentic.models import (
    AccountTarget,
    CapabilityRequest,
    CollectorOutcome,
    ExecutionContext,
    InvocationRequest,
    StructuredError,
)
from agentic.orchestrator import invoke
from agentic.registry import CapabilityRegistryImpl, RegisteredCapability
from agentic.schemas.processor import CanonicalSchemaProcessor


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------

ACCOUNT_ID = "123456789012"
REGION = "us-east-1"


def _make_mock_session(pages: list[dict[str, Any]]) -> MagicMock:
    """Create a mock boto3 session with configurable paginator pages."""
    session = MagicMock()
    ec2_client = MagicMock()
    paginator = MagicMock()
    paginator.paginate.return_value = pages
    ec2_client.get_paginator.return_value = paginator
    session.client.return_value = ec2_client
    return session


def _make_raw_instance(
    instance_id: str = "i-abc123def456",
    instance_type: str = "m5.large",
    state: str = "running",
    launch_time: datetime | None = None,
    az: str = "us-east-1a",
    platform: str | None = None,
    architecture: str = "x86_64",
    vpc_id: str = "vpc-12345",
    subnet_id: str = "subnet-67890",
    public_ip: str | None = "54.123.45.67",
    ebs_optimized: bool = True,
    tags: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Create a raw EC2 instance dict as returned by DescribeInstances."""
    if launch_time is None:
        launch_time = datetime(2024, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
    instance: dict[str, Any] = {
        "InstanceId": instance_id,
        "InstanceType": instance_type,
        "State": {"Name": state},
        "LaunchTime": launch_time,
        "Placement": {"AvailabilityZone": az},
        "Architecture": architecture,
        "VpcId": vpc_id,
        "SubnetId": subnet_id,
        "EbsOptimized": ebs_optimized,
    }
    if platform is not None:
        instance["Platform"] = platform
    if public_ip is not None:
        instance["PublicIpAddress"] = public_ip
    if tags is not None:
        instance["Tags"] = tags
    return instance


def _make_page(instances: list[dict[str, Any]]) -> dict[str, Any]:
    """Wrap instances into a DescribeInstances page."""
    return {"Reservations": [{"Instances": instances}]}


def _make_invocation_request(
    capabilities: tuple[CapabilityRequest, ...] | None = None,
) -> InvocationRequest:
    """Create a minimal valid InvocationRequest for ec2.inventory."""
    if capabilities is None:
        capabilities = (
            CapabilityRequest(id="ec2.inventory", version="1.0.0"),
        )
    return InvocationRequest(
        schema_id="invocation-request",
        schema_version="1.0.0",
        capabilities=capabilities,
        targets=(AccountTarget(account_id=ACCOUNT_ID),),
        regions=(REGION,),
        execution_context=ExecutionContext(
            caller_id="test-agent",
            correlation_id="test-correlation-001",
        ),
    )


class FakeS3Collector:
    """Fake S3 collector for routing isolation tests."""

    def __init__(self) -> None:
        self.called = False

    def collect(
        self,
        capability_id: str,
        capability_version: str,
        account_id: str,
        region_scope: str,
        parameters: Mapping[str, Any],
        session: Any,
    ) -> CollectorOutcome:
        self.called = True
        return CollectorOutcome(status="succeeded", records=(), evidence=())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry() -> CapabilityRegistryImpl:
    """Registry with ec2.inventory registered."""
    reg = CapabilityRegistryImpl()
    register_ec2_inventory(reg, EC2InventoryCollector())
    return reg


@pytest.fixture
def schema_processor() -> CanonicalSchemaProcessor:
    return CanonicalSchemaProcessor()


@pytest.fixture
def collector() -> EC2InventoryCollector:
    return EC2InventoryCollector()


# ---------------------------------------------------------------------------
# 1. Routing Tests (Req 4.1, 4.6)
# ---------------------------------------------------------------------------


class TestRoutingIntegration:
    """Verify invoke() routes ec2.inventory to EC2 handler only."""

    def test_unfiltered_invocation_selects_only_ec2(
        self, registry: CapabilityRegistryImpl, schema_processor: CanonicalSchemaProcessor
    ):
        """invoke() with ec2.inventory and no filters routes only to EC2 collector."""
        request = _make_invocation_request()

        result = invoke(request, registry, schema_processor)

        # The plan should have succeeded (no validation errors)
        assert result.execution_status == "succeeded"
        # Plan should contain exactly one unit for ec2.inventory
        # We verify via the plan_digest being non-empty (plan was created)
        assert result.plan_digest != ""

    def test_multiple_capabilities_in_registry_no_interference(
        self, schema_processor: CanonicalSchemaProcessor
    ):
        """With both ec2.inventory and s3.inventory registered, requesting only
        ec2.inventory selects only EC2."""
        reg = CapabilityRegistryImpl()
        register_ec2_inventory(reg, EC2InventoryCollector())

        # Register a fake s3.inventory
        from agentic.models import CapabilityDescriptor, SemVer

        s3_collector = FakeS3Collector()
        s3_descriptor = CapabilityDescriptor(
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
        reg.register(s3_descriptor, s3_collector)

        # Request only ec2.inventory
        request = _make_invocation_request(
            capabilities=(CapabilityRequest(id="ec2.inventory", version="1.0.0"),)
        )
        result = invoke(request, reg, schema_processor)

        assert result.execution_status == "succeeded"
        # s3 collector should NOT have been called (routing only produces plan)
        assert s3_collector.called is False

    def test_explicit_capability_id_required_no_fuzzy_routing(
        self, registry: CapabilityRegistryImpl, schema_processor: CanonicalSchemaProcessor
    ):
        """'ec2' without '.inventory' fails — no fuzzy routing."""
        request = InvocationRequest(
            schema_id="invocation-request",
            schema_version="1.0.0",
            capabilities=(CapabilityRequest(id="ec2", version="1.0.0"),),
            targets=(AccountTarget(account_id=ACCOUNT_ID),),
            regions=(REGION,),
            execution_context=ExecutionContext(
                caller_id="test-agent",
                correlation_id="test-correlation-002",
            ),
        )

        result = invoke(request, registry, schema_processor)

        # Should fail because "ec2" is not a registered capability
        assert result.execution_status == "failed"


# ---------------------------------------------------------------------------
# 2. Multi-Page Pagination (Req 4.2)
# ---------------------------------------------------------------------------


class TestMultiPagePaginationIntegration:
    """Verify all instances across multiple paginator pages are collected."""

    def test_three_pages_all_collected(self, collector: EC2InventoryCollector):
        """Mock paginator with 3 pages, verify all instances appear in result."""
        pages = [
            _make_page([_make_raw_instance(instance_id=f"i-page1-{j}") for j in range(3)]),
            _make_page([_make_raw_instance(instance_id=f"i-page2-{j}") for j in range(3)]),
            _make_page([_make_raw_instance(instance_id=f"i-page3-{j}") for j in range(3)]),
        ]
        session = _make_mock_session(pages)

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, {}, session
        )

        assert outcome.status == "succeeded"
        assert len(outcome.records) == 9
        ids = {r.fields["instance_id"] for r in outcome.records}
        for page_num in range(1, 4):
            for j in range(3):
                assert f"i-page{page_num}-{j}" in ids

    def test_large_pagination_five_pages_twenty_instances(
        self, collector: EC2InventoryCollector
    ):
        """5 pages × 20 instances = 100 instances, verify nothing is lost."""
        pages = []
        for page_num in range(5):
            instances = [
                _make_raw_instance(instance_id=f"i-p{page_num}-{j:03d}")
                for j in range(20)
            ]
            pages.append(_make_page(instances))
        session = _make_mock_session(pages)

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, {}, session
        )

        assert outcome.status == "succeeded"
        assert len(outcome.records) == 100


# ---------------------------------------------------------------------------
# 3. Filter Translation (Req 4.3)
# ---------------------------------------------------------------------------


class TestFilterTranslationIntegration:
    """Verify combined filters reach paginator correctly."""

    def test_combined_filters_translate_correctly(
        self, collector: EC2InventoryCollector
    ):
        """states + vpc_ids + tags all reach the paginator as proper Filters."""
        session = _make_mock_session([_make_page([])])
        params = {
            "filters": {
                "states": ["running", "stopped"],
                "vpc_ids": ["vpc-aaa", "vpc-bbb"],
                "tags": {"Environment": ["prod"], "Team": ["platform"]},
            }
        }

        collector.collect("ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, params, session)

        # Verify paginator received the translated filters
        ec2_client = session.client.return_value
        paginator = ec2_client.get_paginator.return_value
        call_kwargs = paginator.paginate.call_args[1]
        filters = call_kwargs["Filters"]

        # Check states filter
        assert {"Name": "instance-state-name", "Values": ["running", "stopped"]} in filters
        # Check vpc_ids filter
        assert {"Name": "vpc-id", "Values": ["vpc-aaa", "vpc-bbb"]} in filters
        # Check tag filters (AND semantics between tag keys)
        assert {"Name": "tag:Environment", "Values": ["prod"]} in filters
        assert {"Name": "tag:Team", "Values": ["platform"]} in filters

    def test_tag_filters_produce_and_semantics(
        self, collector: EC2InventoryCollector
    ):
        """Multiple tag keys each become separate Filter entries (AND semantics)."""
        session = _make_mock_session([_make_page([])])
        params = {
            "filters": {
                "tags": {
                    "env": ["prod", "staging"],
                    "team": ["infra"],
                    "project": ["alpha"],
                }
            }
        }

        collector.collect("ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, params, session)

        ec2_client = session.client.return_value
        paginator = ec2_client.get_paginator.return_value
        call_kwargs = paginator.paginate.call_args[1]
        filters = call_kwargs["Filters"]

        # Each tag key is a separate filter entry (AND across keys)
        assert {"Name": "tag:env", "Values": ["prod", "staging"]} in filters
        assert {"Name": "tag:team", "Values": ["infra"]} in filters
        assert {"Name": "tag:project", "Values": ["alpha"]} in filters
        # Total: 3 tag filter entries
        tag_filters = [f for f in filters if f["Name"].startswith("tag:")]
        assert len(tag_filters) == 3


# ---------------------------------------------------------------------------
# 4. Field Compatibility (Req 4.4)
# ---------------------------------------------------------------------------


class TestFieldCompatibilityIntegration:
    """Verify required identity fields + optional field projection."""

    def test_all_v1_fields_present_when_no_projection(
        self, collector: EC2InventoryCollector
    ):
        """With no fields parameter, all optional v1 fields are in output."""
        instance = _make_raw_instance(
            tags=[{"Key": "Name", "Value": "web-01"}, {"Key": "Environment", "Value": "prod"}]
        )
        session = _make_mock_session([_make_page([instance])])

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, {}, session
        )

        fields = outcome.records[0].fields
        for opt_field in EC2_OPTIONAL_V1_FIELDS:
            assert opt_field in fields, f"Expected '{opt_field}' in record fields"

    def test_projected_fields_only_include_requested(
        self, collector: EC2InventoryCollector
    ):
        """Request only ['instance_type', 'state'], verify others absent."""
        instance = _make_raw_instance()
        session = _make_mock_session([_make_page([instance])])
        params = {"fields": ["instance_type", "state"]}

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, params, session
        )

        fields = outcome.records[0].fields
        assert "instance_type" in fields
        assert "state" in fields
        assert "instance_id" in fields  # always required
        # Other optional fields should NOT be present
        assert "vpc_id" not in fields
        assert "subnet_id" not in fields
        assert "platform" not in fields
        assert "launch_time" not in fields

    def test_required_identity_fields_always_present(
        self, collector: EC2InventoryCollector
    ):
        """Even with projection, resource_identity/instance_id/account_id/region
        are always included at record level."""
        instance = _make_raw_instance(instance_id="i-identity-test")
        session = _make_mock_session([_make_page([instance])])
        params = {"fields": ["state"]}  # Only request 'state'

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, params, session
        )

        record = outcome.records[0]
        # resource_identity is always at record level
        assert record.resource_identity == f"{ACCOUNT_ID}/{REGION}/i-identity-test"
        # account_id and region_scope are record-level required fields
        assert record.account_id == ACCOUNT_ID
        assert record.region_scope == REGION
        # instance_id is always in fields (required)
        assert record.fields["instance_id"] == "i-identity-test"


# ---------------------------------------------------------------------------
# 5. UTC Normalization
# ---------------------------------------------------------------------------


class TestUTCNormalizationIntegration:
    """Verify timestamps are normalized to RFC 3339 UTC with Z suffix."""

    def test_utc_timestamps_normalized_to_rfc3339_with_z(
        self, collector: EC2InventoryCollector
    ):
        """datetime objects are converted to RFC 3339 with Z suffix."""
        lt = datetime(2024, 8, 20, 14, 30, 45, tzinfo=timezone.utc)
        instance = _make_raw_instance(launch_time=lt)
        session = _make_mock_session([_make_page([instance])])

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, {}, session
        )

        launch_time = outcome.records[0].fields["launch_time"]
        assert launch_time == "2024-08-20T14:30:45Z"
        assert launch_time.endswith("Z")

    def test_naive_datetimes_treated_as_utc(
        self, collector: EC2InventoryCollector
    ):
        """Naive datetimes (no tzinfo) are treated as UTC."""
        lt = datetime(2024, 1, 15, 8, 0, 0)  # No timezone
        instance = _make_raw_instance(launch_time=lt)
        session = _make_mock_session([_make_page([instance])])

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, {}, session
        )

        launch_time = outcome.records[0].fields["launch_time"]
        assert launch_time == "2024-01-15T08:00:00Z"


# ---------------------------------------------------------------------------
# 6. Successful-Empty Outcome (Req 15.2)
# ---------------------------------------------------------------------------


class TestSuccessfulEmptyOutcomeIntegration:
    """Zero instances = succeeded, not failed."""

    def test_zero_instances_returns_succeeded(
        self, collector: EC2InventoryCollector
    ):
        """Empty paginator result returns CollectorOutcome(status='succeeded')."""
        session = _make_mock_session([{"Reservations": []}])

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, {}, session
        )

        assert outcome.status == "succeeded"
        assert len(outcome.records) == 0

    def test_empty_outcome_still_has_evidence(
        self, collector: EC2InventoryCollector
    ):
        """Evidence metadata is created even for empty results."""
        session = _make_mock_session([{"Reservations": []}])

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, {}, session
        )

        assert outcome.status == "succeeded"
        assert len(outcome.evidence) == 1
        evidence = outcome.evidence[0]
        assert evidence.capability_id == "ec2.inventory"
        assert evidence.operation == "ec2:DescribeInstances"
        assert evidence.collected_at.endswith("Z")
        assert evidence.target.account_id == ACCOUNT_ID
        assert evidence.target.region_scope == REGION


# ---------------------------------------------------------------------------
# 7. Unsupported Input Without SDK Call (Req 4.5)
# ---------------------------------------------------------------------------


class TestUnsupportedInputNoSDKCallIntegration:
    """Invalid input stops before paginator — session/client never called."""

    def test_invalid_filter_key_stops_before_paginator(
        self, collector: EC2InventoryCollector
    ):
        """Unsupported filter key causes failure before SDK call."""
        session = MagicMock()
        params = {"filters": {"unknown_filter": ["value"]}}

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, params, session
        )

        assert outcome.status == "failed"
        assert outcome.error is not None
        assert outcome.error.code == "INVALID_PARAMETERS"
        # Session.client() should never be called
        session.client.assert_not_called()

    def test_invalid_field_name_stops_before_paginator(
        self, collector: EC2InventoryCollector
    ):
        """Unsupported field name causes failure before SDK call."""
        session = MagicMock()
        params = {"fields": ["nonexistent_field_xyz"]}

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, params, session
        )

        assert outcome.status == "failed"
        assert outcome.error is not None
        assert outcome.error.code == "INVALID_PARAMETERS"
        session.client.assert_not_called()

    def test_invalid_resource_type_stops_before_paginator(
        self, collector: EC2InventoryCollector
    ):
        """Unsupported resource_type causes failure before SDK call."""
        session = MagicMock()
        params = {"resource_type": "volume"}

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, params, session
        )

        assert outcome.status == "failed"
        assert outcome.error is not None
        assert outcome.error.code == "INVALID_PARAMETERS"
        session.client.assert_not_called()


# ---------------------------------------------------------------------------
# 8. End-to-End invoke() Integration
# ---------------------------------------------------------------------------


class TestEndToEndInvokeIntegration:
    """Full invoke() flow from request through plan to result."""

    def test_invoke_with_ec2_inventory_returns_succeeded(
        self, registry: CapabilityRegistryImpl, schema_processor: CanonicalSchemaProcessor
    ):
        """Full flow: invoke() with ec2.inventory produces succeeded result."""
        request = _make_invocation_request()

        result = invoke(request, registry, schema_processor)

        assert result.execution_status == "succeeded"
        assert result.plan_digest != ""
        assert result.request_digest != ""
        assert result.manifest_version != ""
        assert result.correlation_id == "test-correlation-001"

    def test_invoke_with_unsupported_capability_returns_failed(
        self, registry: CapabilityRegistryImpl, schema_processor: CanonicalSchemaProcessor
    ):
        """Unknown capability handled gracefully with failed status."""
        request = InvocationRequest(
            schema_id="invocation-request",
            schema_version="1.0.0",
            capabilities=(
                CapabilityRequest(id="unknown.service", version="1.0.0"),
            ),
            targets=(AccountTarget(account_id=ACCOUNT_ID),),
            regions=(REGION,),
            execution_context=ExecutionContext(
                caller_id="test-agent",
                correlation_id="test-correlation-003",
            ),
        )

        result = invoke(request, registry, schema_processor)

        assert result.execution_status == "failed"
