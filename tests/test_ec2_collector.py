"""
Tests for EC2InventoryCollector typed adapter.

Covers:
- Mock boto3 paginator returning instances
- Filter translation to DescribeInstances format
- Field projection (subset of fields)
- Deduplication by resource_identity
- Sorting by (account_id, region, instance_id)
- Empty result returns succeeded status
- AWS error returns failed with StructuredError
- resource_identity format
- UTC timestamp normalization
- Local predicate check (defensive filtering)

Requirements traced: 4.2, 4.3, 4.4, 8.1, 9.2, 16.6
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from agentic.ec2_collector import (
    EC2InventoryCollector,
    _apply_field_projection,
    _matches_local_predicate,
    _normalize_launch_time,
    _translate_filters,
)
from agentic.models import (
    CollectorOutcome,
    Evidence,
    ResourceRecord,
    StructuredError,
    TargetPair,
)


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


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


def _make_mock_session(pages: list[dict[str, Any]] | None = None) -> MagicMock:
    """Create a mock boto3 session with configurable paginator pages."""
    session = MagicMock()
    ec2_client = MagicMock()
    paginator = MagicMock()

    if pages is None:
        pages = [{"Reservations": []}]

    paginator.paginate.return_value = pages
    ec2_client.get_paginator.return_value = paginator
    session.client.return_value = ec2_client
    return session


def _make_page(instances: list[dict[str, Any]]) -> dict[str, Any]:
    """Wrap instances into a DescribeInstances page."""
    return {"Reservations": [{"Instances": instances}]}


@pytest.fixture
def collector() -> EC2InventoryCollector:
    return EC2InventoryCollector()


@pytest.fixture
def default_params() -> dict[str, Any]:
    return {}


ACCOUNT_ID = "123456789012"
REGION = "us-east-1"


# ---------------------------------------------------------------------------
# Test: Mock paginator returning instances (Req 4.2)
# ---------------------------------------------------------------------------


class TestPaginatorCollection:
    """Verify paginator exhausts all pages and collects instances."""

    def test_single_page_single_instance(self, collector: EC2InventoryCollector):
        """Single page with one instance returns one record."""
        instance = _make_raw_instance()
        session = _make_mock_session([_make_page([instance])])

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, {}, session
        )

        assert outcome.status == "succeeded"
        assert len(outcome.records) == 1
        assert outcome.records[0].fields["instance_id"] == "i-abc123def456"

    def test_multiple_pages(self, collector: EC2InventoryCollector):
        """Multiple pages all get collected."""
        i1 = _make_raw_instance(instance_id="i-page1")
        i2 = _make_raw_instance(instance_id="i-page2")
        session = _make_mock_session([_make_page([i1]), _make_page([i2])])

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, {}, session
        )

        assert outcome.status == "succeeded"
        assert len(outcome.records) == 2

    def test_multiple_reservations(self, collector: EC2InventoryCollector):
        """Multiple reservations within a page are all collected."""
        i1 = _make_raw_instance(instance_id="i-res1")
        i2 = _make_raw_instance(instance_id="i-res2")
        page = {
            "Reservations": [
                {"Instances": [i1]},
                {"Instances": [i2]},
            ]
        }
        session = _make_mock_session([page])

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, {}, session
        )

        assert outcome.status == "succeeded"
        assert len(outcome.records) == 2


# ---------------------------------------------------------------------------
# Test: Filter translation (Req 4.3)
# ---------------------------------------------------------------------------


class TestFilterTranslation:
    """Verify filters are correctly translated to DescribeInstances format."""

    def test_instance_ids_filter(self):
        """instance_ids translates to instance-id filter."""
        filters = {"instance_ids": ["i-abc", "i-def"]}
        result = _translate_filters(filters)
        assert {"Name": "instance-id", "Values": ["i-abc", "i-def"]} in result

    def test_states_filter(self):
        """states translates to instance-state-name filter."""
        filters = {"states": ["running", "stopped"]}
        result = _translate_filters(filters)
        assert {"Name": "instance-state-name", "Values": ["running", "stopped"]} in result

    def test_vpc_ids_filter(self):
        """vpc_ids translates to vpc-id filter."""
        filters = {"vpc_ids": ["vpc-123"]}
        result = _translate_filters(filters)
        assert {"Name": "vpc-id", "Values": ["vpc-123"]} in result

    def test_subnet_ids_filter(self):
        """subnet_ids translates to subnet-id filter."""
        filters = {"subnet_ids": ["subnet-abc"]}
        result = _translate_filters(filters)
        assert {"Name": "subnet-id", "Values": ["subnet-abc"]} in result

    def test_availability_zones_filter(self):
        """availability_zones translates to availability-zone filter."""
        filters = {"availability_zones": ["us-east-1a", "us-east-1b"]}
        result = _translate_filters(filters)
        assert {"Name": "availability-zone", "Values": ["us-east-1a", "us-east-1b"]} in result

    def test_tags_filter(self):
        """tags translates to tag:<key> filters (AND across keys)."""
        filters = {"tags": {"env": ["prod", "staging"], "team": ["infra"]}}
        result = _translate_filters(filters)
        assert {"Name": "tag:env", "Values": ["prod", "staging"]} in result
        assert {"Name": "tag:team", "Values": ["infra"]} in result

    def test_combined_filters(self):
        """Multiple filter categories produce combined AWS filters."""
        filters = {
            "states": ["running"],
            "vpc_ids": ["vpc-123"],
            "tags": {"Name": ["web"]},
        }
        result = _translate_filters(filters)
        assert len(result) == 3

    def test_empty_filters(self):
        """Empty filters produce empty AWS filters list."""
        result = _translate_filters({})
        assert result == []

    def test_filters_passed_to_paginator(self, collector: EC2InventoryCollector):
        """Translated filters are passed to paginator.paginate()."""
        session = _make_mock_session([_make_page([])])
        params = {"filters": {"states": ["running"]}}

        collector.collect("ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, params, session)

        ec2_client = session.client.return_value
        paginator = ec2_client.get_paginator.return_value
        call_kwargs = paginator.paginate.call_args[1]
        assert "Filters" in call_kwargs
        assert {"Name": "instance-state-name", "Values": ["running"]} in call_kwargs["Filters"]


# ---------------------------------------------------------------------------
# Test: Field projection (Req 4.4)
# ---------------------------------------------------------------------------


class TestFieldProjection:
    """Verify field projection limits output to requested fields."""

    def test_no_fields_includes_all(self, collector: EC2InventoryCollector):
        """No fields parameter includes all optional v1 fields."""
        instance = _make_raw_instance()
        session = _make_mock_session([_make_page([instance])])

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, {}, session
        )

        fields = outcome.records[0].fields
        assert "instance_type" in fields
        assert "state" in fields
        assert "launch_time" in fields
        assert "platform" in fields
        assert "vpc_id" in fields

    def test_fields_subset(self, collector: EC2InventoryCollector):
        """Fields parameter limits output to requested fields + instance_id."""
        instance = _make_raw_instance()
        session = _make_mock_session([_make_page([instance])])
        params = {"fields": ["instance_type", "state"]}

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, params, session
        )

        fields = outcome.records[0].fields
        assert "instance_id" in fields  # always included
        assert "instance_type" in fields
        assert "state" in fields
        # Other optional fields should NOT be present
        assert "vpc_id" not in fields
        assert "subnet_id" not in fields
        assert "platform" not in fields

    def test_projection_internal_function(self):
        """_apply_field_projection correctly filters fields."""
        instance_fields = {
            "instance_id": "i-abc",
            "instance_type": "m5.large",
            "state": "running",
            "vpc_id": "vpc-123",
            "name": "test",
        }
        result = _apply_field_projection(instance_fields, ["instance_type"])
        assert "instance_id" in result
        assert "instance_type" in result
        assert "vpc_id" not in result
        assert "name" not in result


# ---------------------------------------------------------------------------
# Test: Deduplication (Req 16.6)
# ---------------------------------------------------------------------------


class TestDeduplication:
    """Verify records are deduplicated by resource_identity."""

    def test_duplicate_instances_deduplicated(self, collector: EC2InventoryCollector):
        """Duplicate instance IDs across pages are deduplicated."""
        i1 = _make_raw_instance(instance_id="i-dup001")
        i2 = _make_raw_instance(instance_id="i-dup001")  # same ID
        session = _make_mock_session([_make_page([i1, i2])])

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, {}, session
        )

        assert outcome.status == "succeeded"
        assert len(outcome.records) == 1
        assert outcome.records[0].fields["instance_id"] == "i-dup001"

    def test_different_instances_not_deduplicated(self, collector: EC2InventoryCollector):
        """Different instance IDs are not deduplicated."""
        i1 = _make_raw_instance(instance_id="i-unique1")
        i2 = _make_raw_instance(instance_id="i-unique2")
        session = _make_mock_session([_make_page([i1, i2])])

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, {}, session
        )

        assert len(outcome.records) == 2


# ---------------------------------------------------------------------------
# Test: Sorting (Req 4.4)
# ---------------------------------------------------------------------------


class TestSorting:
    """Verify records are sorted by (account_id, region, instance_id)."""

    def test_sorted_by_instance_id(self, collector: EC2InventoryCollector):
        """Records are sorted by instance_id within same account/region."""
        i_c = _make_raw_instance(instance_id="i-charlie")
        i_a = _make_raw_instance(instance_id="i-alpha")
        i_b = _make_raw_instance(instance_id="i-bravo")
        session = _make_mock_session([_make_page([i_c, i_a, i_b])])

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, {}, session
        )

        ids = [r.fields["instance_id"] for r in outcome.records]
        assert ids == ["i-alpha", "i-bravo", "i-charlie"]


# ---------------------------------------------------------------------------
# Test: Empty result (Req 9.2)
# ---------------------------------------------------------------------------


class TestEmptyResult:
    """Verify empty result returns succeeded status with zero records."""

    def test_empty_pages_returns_succeeded(self, collector: EC2InventoryCollector):
        """No instances found returns succeeded with empty records tuple."""
        session = _make_mock_session([{"Reservations": []}])

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, {}, session
        )

        assert outcome.status == "succeeded"
        assert len(outcome.records) == 0
        assert len(outcome.evidence) == 1

    def test_empty_result_has_evidence(self, collector: EC2InventoryCollector):
        """Empty collection still produces evidence metadata."""
        session = _make_mock_session([{"Reservations": []}])

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, {}, session
        )

        assert len(outcome.evidence) == 1
        ev = outcome.evidence[0]
        assert ev.capability_id == "ec2.inventory"
        assert ev.operation == "ec2:DescribeInstances"


# ---------------------------------------------------------------------------
# Test: AWS error returns failed with StructuredError (Req 9.2)
# ---------------------------------------------------------------------------


class TestAWSErrorHandling:
    """Verify AWS exceptions produce CollectorOutcome with status='failed'."""

    def test_generic_exception_returns_failed(self, collector: EC2InventoryCollector):
        """Generic exception produces failed outcome with StructuredError."""
        session = MagicMock()
        ec2_client = MagicMock()
        paginator = MagicMock()
        paginator.paginate.side_effect = Exception("Connection timeout")
        ec2_client.get_paginator.return_value = paginator
        session.client.return_value = ec2_client

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, {}, session
        )

        assert outcome.status == "failed"
        assert outcome.error is not None
        assert isinstance(outcome.error, StructuredError)
        assert outcome.error.capability_id == "ec2.inventory"

    def test_boto_client_error_returns_structured_error(self, collector: EC2InventoryCollector):
        """Botocore ClientError produces StructuredError with correct code."""
        session = MagicMock()
        ec2_client = MagicMock()
        paginator = MagicMock()

        # Simulate a botocore ClientError
        error = Exception("Access denied")
        error.response = {  # type: ignore[attr-defined]
            "Error": {"Code": "UnauthorizedOperation", "Message": "Not allowed"}
        }
        paginator.paginate.side_effect = error
        ec2_client.get_paginator.return_value = paginator
        session.client.return_value = ec2_client

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, {}, session
        )

        assert outcome.status == "failed"
        assert outcome.error is not None
        assert outcome.error.code == "UnauthorizedOperation"
        assert outcome.error.category == "permission-denied"
        assert outcome.error.retryable is False

    def test_throttling_error_is_retryable(self, collector: EC2InventoryCollector):
        """Throttling errors are marked as retryable."""
        session = MagicMock()
        ec2_client = MagicMock()
        paginator = MagicMock()

        error = Exception("Rate exceeded")
        error.response = {  # type: ignore[attr-defined]
            "Error": {"Code": "Throttling", "Message": "Rate exceeded"}
        }
        paginator.paginate.side_effect = error
        ec2_client.get_paginator.return_value = paginator
        session.client.return_value = ec2_client

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, {}, session
        )

        assert outcome.status == "failed"
        assert outcome.error is not None
        assert outcome.error.category == "throttled"
        assert outcome.error.retryable is True


# ---------------------------------------------------------------------------
# Test: resource_identity format (Req 16.6)
# ---------------------------------------------------------------------------


class TestResourceIdentity:
    """Verify resource_identity format is account_id/region/instance_id."""

    def test_resource_identity_format(self, collector: EC2InventoryCollector):
        """resource_identity follows {account_id}/{region}/{instance_id} format."""
        instance = _make_raw_instance(instance_id="i-format001")
        session = _make_mock_session([_make_page([instance])])

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, {}, session
        )

        record = outcome.records[0]
        expected_identity = f"{ACCOUNT_ID}/{REGION}/i-format001"
        assert record.resource_identity == expected_identity

    def test_resource_identity_uses_invocation_context(self, collector: EC2InventoryCollector):
        """resource_identity uses account_id and region from invocation, not from instance."""
        instance = _make_raw_instance(instance_id="i-ctx001")
        session = _make_mock_session([_make_page([instance])])

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", "999888777666", "eu-west-1", {}, session
        )

        record = outcome.records[0]
        assert record.resource_identity == "999888777666/eu-west-1/i-ctx001"
        assert record.account_id == "999888777666"
        assert record.region_scope == "eu-west-1"


# ---------------------------------------------------------------------------
# Test: UTC timestamp normalization (Req 4.4)
# ---------------------------------------------------------------------------


class TestTimestampNormalization:
    """Verify launch_time is normalized to UTC RFC 3339 with 'Z' suffix."""

    def test_utc_datetime_normalized(self):
        """UTC datetime converts to RFC 3339 with Z."""
        dt = datetime(2024, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = _normalize_launch_time(dt)
        assert result == "2024-06-15T10:30:00Z"

    def test_naive_datetime_treated_as_utc(self):
        """Naive datetime (no tzinfo) is treated as UTC."""
        dt = datetime(2024, 1, 1, 0, 0, 0)
        result = _normalize_launch_time(dt)
        assert result == "2024-01-01T00:00:00Z"

    def test_launch_time_in_record(self, collector: EC2InventoryCollector):
        """Collected record has launch_time in RFC 3339 UTC format."""
        lt = datetime(2024, 3, 20, 15, 45, 30, tzinfo=timezone.utc)
        instance = _make_raw_instance(launch_time=lt)
        session = _make_mock_session([_make_page([instance])])

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, {}, session
        )

        assert outcome.records[0].fields["launch_time"] == "2024-03-20T15:45:30Z"


# ---------------------------------------------------------------------------
# Test: Local predicate check (Req 4.3)
# ---------------------------------------------------------------------------


class TestLocalPredicate:
    """Verify local predicate filters instances defensively."""

    def test_predicate_passes_matching_state(self):
        """Instance matching state filter passes predicate."""
        fields = {"state": "running", "instance_id": "i-1"}
        assert _matches_local_predicate(fields, {"states": ["running", "stopped"]})

    def test_predicate_fails_non_matching_state(self):
        """Instance not matching state filter fails predicate."""
        fields = {"state": "terminated", "instance_id": "i-1"}
        assert not _matches_local_predicate(fields, {"states": ["running"]})

    def test_predicate_passes_matching_vpc(self):
        """Instance matching vpc_ids filter passes predicate."""
        fields = {"vpc_id": "vpc-123", "instance_id": "i-1"}
        assert _matches_local_predicate(fields, {"vpc_ids": ["vpc-123", "vpc-456"]})

    def test_predicate_fails_non_matching_vpc(self):
        """Instance not matching vpc_ids filter fails predicate."""
        fields = {"vpc_id": "vpc-999", "instance_id": "i-1"}
        assert not _matches_local_predicate(fields, {"vpc_ids": ["vpc-123"]})

    def test_predicate_empty_filters_passes(self):
        """Empty filters always pass."""
        fields = {"state": "running", "instance_id": "i-1"}
        assert _matches_local_predicate(fields, {})

    def test_predicate_multiple_filters_and_semantics(self):
        """Multiple filter categories use AND semantics."""
        fields = {
            "state": "running",
            "vpc_id": "vpc-123",
            "instance_id": "i-1",
        }
        # Passes both
        assert _matches_local_predicate(
            fields, {"states": ["running"], "vpc_ids": ["vpc-123"]}
        )
        # Fails one
        assert not _matches_local_predicate(
            fields, {"states": ["running"], "vpc_ids": ["vpc-999"]}
        )

    def test_local_predicate_filters_in_collector(self, collector: EC2InventoryCollector):
        """Collector applies local predicate to filter mismatched instances."""
        # Instance has state=terminated but filter expects running
        # Since we use server-side filters, in practice this shouldn't happen.
        # But we test the defensive check by not passing Filters to paginator mock
        i_match = _make_raw_instance(instance_id="i-match", state="running")
        i_mismatch = _make_raw_instance(instance_id="i-mismatch", state="terminated")

        # Mock: paginator returns both (simulating server not filtering correctly)
        session = _make_mock_session([_make_page([i_match, i_mismatch])])
        params = {"filters": {"states": ["running"]}}

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, params, session
        )

        assert outcome.status == "succeeded"
        ids = [r.fields["instance_id"] for r in outcome.records]
        assert "i-match" in ids
        assert "i-mismatch" not in ids


# ---------------------------------------------------------------------------
# Test: Evidence metadata (Req 8.1)
# ---------------------------------------------------------------------------


class TestEvidenceMetadata:
    """Verify Evidence is created with correct metadata."""

    def test_evidence_target(self, collector: EC2InventoryCollector):
        """Evidence target contains account_id and region."""
        instance = _make_raw_instance()
        session = _make_mock_session([_make_page([instance])])

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, {}, session
        )

        ev = outcome.evidence[0]
        assert ev.target == TargetPair(account_id=ACCOUNT_ID, region_scope=REGION)

    def test_evidence_capability_fields(self, collector: EC2InventoryCollector):
        """Evidence has correct capability_id, capability_version, collector_version."""
        session = _make_mock_session([_make_page([_make_raw_instance()])])

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, {}, session
        )

        ev = outcome.evidence[0]
        assert ev.capability_id == "ec2.inventory"
        assert ev.capability_version == "1.0.0"
        assert ev.collector_version == "1.0.0"

    def test_evidence_operation(self, collector: EC2InventoryCollector):
        """Evidence operation is ec2:DescribeInstances."""
        session = _make_mock_session([_make_page([_make_raw_instance()])])

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, {}, session
        )

        assert outcome.evidence[0].operation == "ec2:DescribeInstances"

    def test_evidence_collected_at_is_utc_rfc3339(self, collector: EC2InventoryCollector):
        """Evidence collected_at is in RFC 3339 UTC format with Z suffix."""
        session = _make_mock_session([_make_page([_make_raw_instance()])])

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, {}, session
        )

        collected_at = outcome.evidence[0].collected_at
        assert collected_at.endswith("Z")
        # Verify it's parseable as a valid timestamp
        datetime.strptime(collected_at, "%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Test: Parameter validation failure (Req 4.5, 9.2)
# ---------------------------------------------------------------------------


class TestParameterValidation:
    """Verify invalid parameters return failed CollectorOutcome."""

    def test_invalid_filter_returns_failed(self, collector: EC2InventoryCollector):
        """Unsupported filter key causes failed outcome before AWS call."""
        session = MagicMock()
        params = {"filters": {"unsupported_key": ["value"]}}

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, params, session
        )

        assert outcome.status == "failed"
        assert outcome.error is not None
        assert outcome.error.code == "INVALID_PARAMETERS"
        # Paginator should NOT have been called
        session.client.assert_not_called()

    def test_invalid_field_returns_failed(self, collector: EC2InventoryCollector):
        """Unsupported field name causes failed outcome."""
        session = MagicMock()
        params = {"fields": ["nonexistent_field"]}

        outcome = collector.collect(
            "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, params, session
        )

        assert outcome.status == "failed"
        assert outcome.error is not None
        assert outcome.error.code == "INVALID_PARAMETERS"
