# Feature: agentic-aws-assessment, Property 5: EC2 inventory matches the reference model
# Validates: Requirements 4.2, 4.3, 4.4
"""
Property-based test for EC2 inventory reference model matching.

This test validates that for ALL finite paginated EC2 response sets,
supported filter combinations, and supported field selections,
`EC2InventoryCollector.collect()` produces output that matches a simple
reference model implementing the same filtering, projection,
deduplication, and sorting logic.

Key invariants:
1. Same records: collector output contains exactly the same instances as
   the reference model
2. Same order: records are in the same sorted order
3. Same fields: each record has exactly the same fields (after projection)
4. Correct resource_identity: format is {account_id}/{region}/{instance_id}
5. Correct deduplication: no duplicate resource_identity values
6. Status is always "succeeded" when no AWS error occurs
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import hypothesis.strategies as st
from hypothesis import HealthCheck, given, settings

from agentic.ec2_collector import EC2InventoryCollector
from agentic.ec2_contract import EC2_OPTIONAL_V1_FIELDS


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACCOUNT_ID = "123456789012"
REGION = "us-east-1"

_STATES = ["running", "stopped", "terminated", "pending"]
_AZS = ["us-east-1a", "us-east-1b", "us-east-1c"]
_ARCHITECTURES = ["x86_64", "arm64"]
_PLATFORMS = ["Linux", "Windows"]
_INSTANCE_TYPES = ["t3.micro", "m5.large", "c5.xlarge", "r5.2xlarge"]


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------


@st.composite
def ec2_instance(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a realistic EC2 instance dict as returned by DescribeInstances."""
    instance_id = "i-" + draw(
        st.text(alphabet="0123456789abcdef", min_size=12, max_size=12)
    )
    state = draw(st.sampled_from(_STATES))
    vpc_id = "vpc-" + draw(
        st.text(alphabet="0123456789abcdef", min_size=8, max_size=8)
    )
    subnet_id = "subnet-" + draw(
        st.text(alphabet="0123456789abcdef", min_size=8, max_size=8)
    )
    az = draw(st.sampled_from(_AZS))
    architecture = draw(st.sampled_from(_ARCHITECTURES))
    platform = draw(st.sampled_from(_PLATFORMS))
    instance_type = draw(st.sampled_from(_INSTANCE_TYPES))
    ebs_optimized = draw(st.booleans())
    public_ip = draw(
        st.one_of(
            st.none(),
            st.builds(
                lambda a, b, c, d: f"{a}.{b}.{c}.{d}",
                st.integers(1, 254),
                st.integers(0, 255),
                st.integers(0, 255),
                st.integers(1, 254),
            ),
        )
    )

    # Generate 0-3 tags including optional Name/Environment
    tags: list[dict[str, str]] = []
    if draw(st.booleans()):
        tags.append({"Key": "Name", "Value": draw(st.sampled_from(["web", "api", "db", "cache"]))})
    if draw(st.booleans()):
        tags.append({"Key": "Environment", "Value": draw(st.sampled_from(["prod", "staging", "dev"]))})

    launch_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    instance: dict[str, Any] = {
        "InstanceId": instance_id,
        "InstanceType": instance_type,
        "State": {"Name": state},
        "LaunchTime": launch_time,
        "Placement": {"AvailabilityZone": az},
        "Architecture": architecture,
        "Platform": platform,
        "VpcId": vpc_id,
        "SubnetId": subnet_id,
        "EbsOptimized": ebs_optimized,
    }
    if public_ip is not None:
        instance["PublicIpAddress"] = public_ip
    if tags:
        instance["Tags"] = tags

    return instance


@st.composite
def paginated_responses(draw: st.DrawFn) -> list[dict[str, Any]]:
    """Generate 1-5 pages, each with 0-10 instances."""
    num_pages = draw(st.integers(min_value=1, max_value=5))
    pages: list[dict[str, Any]] = []
    for _ in range(num_pages):
        num_instances = draw(st.integers(min_value=0, max_value=10))
        instances = draw(
            st.lists(ec2_instance(), min_size=num_instances, max_size=num_instances)
        )
        pages.append({"Reservations": [{"Instances": instances}]})
    return pages


@st.composite
def filter_combination(
    draw: st.DrawFn, all_instances: list[dict[str, Any]]
) -> dict[str, Any]:
    """Generate a random subset of supported filters derived from instance data."""
    filters: dict[str, Any] = {}

    # Collect possible values from instances for realistic filter generation
    all_states = list({inst["State"]["Name"] for inst in all_instances}) or _STATES
    all_vpcs = list({inst["VpcId"] for inst in all_instances}) or ["vpc-00000000"]
    all_subnets = list({inst["SubnetId"] for inst in all_instances}) or ["subnet-00000000"]
    all_azs = list({inst["Placement"]["AvailabilityZone"] for inst in all_instances}) or _AZS
    all_ids = list({inst["InstanceId"] for inst in all_instances}) or ["i-000000000000"]

    # Randomly include each filter category
    if draw(st.booleans()):
        n = draw(st.integers(min_value=1, max_value=min(3, len(all_ids))))
        filters["instance_ids"] = draw(
            st.lists(st.sampled_from(all_ids), min_size=n, max_size=n, unique=True)
        )

    if draw(st.booleans()):
        n = draw(st.integers(min_value=1, max_value=min(3, len(all_states))))
        filters["states"] = draw(
            st.lists(st.sampled_from(all_states), min_size=n, max_size=n, unique=True)
        )

    if draw(st.booleans()):
        n = draw(st.integers(min_value=1, max_value=min(3, len(all_vpcs))))
        filters["vpc_ids"] = draw(
            st.lists(st.sampled_from(all_vpcs), min_size=n, max_size=n, unique=True)
        )

    if draw(st.booleans()):
        n = draw(st.integers(min_value=1, max_value=min(3, len(all_subnets))))
        filters["subnet_ids"] = draw(
            st.lists(st.sampled_from(all_subnets), min_size=n, max_size=n, unique=True)
        )

    if draw(st.booleans()):
        n = draw(st.integers(min_value=1, max_value=min(3, len(all_azs))))
        filters["availability_zones"] = draw(
            st.lists(st.sampled_from(all_azs), min_size=n, max_size=n, unique=True)
        )

    # Tag filters - use Name and Environment since those are mapped in the collector
    if draw(st.booleans()):
        tags: dict[str, list[str]] = {}
        if draw(st.booleans()):
            tags["Name"] = draw(
                st.lists(
                    st.sampled_from(["web", "api", "db", "cache"]),
                    min_size=1,
                    max_size=3,
                    unique=True,
                )
            )
        if draw(st.booleans()):
            tags["Environment"] = draw(
                st.lists(
                    st.sampled_from(["prod", "staging", "dev"]),
                    min_size=1,
                    max_size=3,
                    unique=True,
                )
            )
        if tags:
            filters["tags"] = tags

    return filters


@st.composite
def field_projection(draw: st.DrawFn) -> list[str] | None:
    """Generate a random subset of optional v1 fields or None (all fields)."""
    if draw(st.booleans()):
        # None means include all fields
        return None
    # Random subset of optional fields
    n = draw(st.integers(min_value=1, max_value=len(EC2_OPTIONAL_V1_FIELDS)))
    return draw(
        st.lists(
            st.sampled_from(list(EC2_OPTIONAL_V1_FIELDS)),
            min_size=n,
            max_size=n,
            unique=True,
        )
    )


@st.composite
def ec2_test_scenario(draw: st.DrawFn):
    """
    Generate a complete test scenario:
    (pages, filters, field_projection)
    """
    pages = draw(paginated_responses())

    # Collect all instances from all pages for filter generation
    all_instances: list[dict[str, Any]] = []
    for page in pages:
        for reservation in page.get("Reservations", []):
            for inst in reservation.get("Instances", []):
                all_instances.append(inst)

    filters = draw(filter_combination(all_instances))
    fields = draw(field_projection())

    return (pages, filters, fields)


# ---------------------------------------------------------------------------
# Reference Model
# ---------------------------------------------------------------------------


def _reference_normalize_instance(
    raw_instance: dict[str, Any],
) -> dict[str, Any]:
    """
    Simple reference normalization matching the collector's logic.
    """
    tags = {t["Key"]: t["Value"] for t in raw_instance.get("Tags", [])}
    launch_time = raw_instance.get("LaunchTime")

    if isinstance(launch_time, datetime):
        if launch_time.tzinfo is None:
            lt_str = launch_time.replace(tzinfo=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        else:
            lt_str = launch_time.astimezone(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
    elif isinstance(launch_time, str):
        lt_str = launch_time
    else:
        lt_str = ""

    return {
        "instance_id": raw_instance["InstanceId"],
        "instance_type": raw_instance.get("InstanceType", ""),
        "state": raw_instance.get("State", {}).get("Name", ""),
        "launch_time": lt_str,
        "platform": raw_instance.get("Platform", "Linux"),
        "architecture": raw_instance.get("Architecture", ""),
        "availability_zone": raw_instance.get("Placement", {}).get(
            "AvailabilityZone", ""
        ),
        "vpc_id": raw_instance.get("VpcId", ""),
        "subnet_id": raw_instance.get("SubnetId", ""),
        "public_ip": raw_instance.get("PublicIpAddress", None),
        "ebs_optimized": raw_instance.get("EbsOptimized", False),
        "name": tags.get("Name", ""),
        "environment": tags.get("Environment", "") or tags.get("Env", ""),
    }


def _reference_matches_filters(
    fields: dict[str, Any], filters: dict[str, Any]
) -> bool:
    """
    Simple reference filter predicate.
    AND across categories, OR within lists, AND across tag keys.
    """
    if not filters:
        return True

    if "instance_ids" in filters:
        if fields["instance_id"] not in filters["instance_ids"]:
            return False

    if "states" in filters:
        if fields["state"] not in filters["states"]:
            return False

    if "vpc_ids" in filters:
        if fields["vpc_id"] not in filters["vpc_ids"]:
            return False

    if "subnet_ids" in filters:
        if fields["subnet_id"] not in filters["subnet_ids"]:
            return False

    if "availability_zones" in filters:
        if fields["availability_zone"] not in filters["availability_zones"]:
            return False

    if "tags" in filters:
        tag_filters = filters["tags"]
        for key, values in tag_filters.items():
            # Map tag keys to normalized field names
            tag_field_map = {
                "Name": "name",
                "Environment": "environment",
                "Env": "environment",
            }
            field_name = tag_field_map.get(key)
            if field_name:
                if fields.get(field_name, "") not in values:
                    return False
            # For unknown tag keys, we cannot verify locally (same as collector)

    return True


def _reference_apply_projection(
    fields: dict[str, Any], requested_fields: list[str] | None
) -> dict[str, Any]:
    """
    Simple reference field projection.
    If requested_fields is None/empty, include all fields.
    Otherwise include instance_id + requested optional fields.
    """
    if requested_fields is None or len(requested_fields) == 0:
        return dict(fields)

    projected: dict[str, Any] = {"instance_id": fields["instance_id"]}
    for f in requested_fields:
        if f in fields:
            projected[f] = fields[f]
    return projected


def reference_model(
    pages: list[dict[str, Any]],
    filters: dict[str, Any],
    requested_fields: list[str] | None,
    account_id: str,
    region: str,
) -> list[dict[str, Any]]:
    """
    Reference model implementation:
    1. Collect all instances from all pages
    2. Normalize each instance
    3. Apply filter predicates
    4. Apply field projection
    5. Deduplicate by resource_identity
    6. Sort by (account_id, region, instance_id)

    Returns list of dicts with keys: resource_identity, fields
    """
    # Step 1: Collect all instances from all pages
    all_instances: list[dict[str, Any]] = []
    for page in pages:
        for reservation in page.get("Reservations", []):
            for inst in reservation.get("Instances", []):
                all_instances.append(inst)

    # Step 2 & 3: Normalize and filter
    passing_instances: list[dict[str, Any]] = []
    for raw in all_instances:
        normalized = _reference_normalize_instance(raw)
        if _reference_matches_filters(normalized, filters):
            passing_instances.append(normalized)

    # Step 4 & 5: Project and deduplicate
    seen_identities: set[str] = set()
    results: list[dict[str, Any]] = []
    for fields in passing_instances:
        resource_identity = f"{account_id}/{region}/{fields['instance_id']}"
        if resource_identity in seen_identities:
            continue
        seen_identities.add(resource_identity)

        projected = _reference_apply_projection(fields, requested_fields)
        results.append(
            {"resource_identity": resource_identity, "fields": projected}
        )

    # Step 6: Sort by (account_id, region, instance_id)
    results.sort(key=lambda r: r["fields"]["instance_id"])

    return results


# ---------------------------------------------------------------------------
# Mock Session
# ---------------------------------------------------------------------------


def _make_mock_session(pages: list[dict[str, Any]]) -> MagicMock:
    """Create a mock boto3 session that returns the generated pages."""
    session = MagicMock()
    ec2_client = MagicMock()
    paginator = MagicMock()
    paginator.paginate.return_value = pages
    ec2_client.get_paginator.return_value = paginator
    session.client.return_value = ec2_client
    return session


# ---------------------------------------------------------------------------
# Property Test
# ---------------------------------------------------------------------------


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(scenario=ec2_test_scenario())
def test_ec2_inventory_matches_reference_model(scenario: tuple) -> None:
    """
    Property 5: EC2 inventory matches the reference model.

    **Validates: Requirements 4.2, 4.3, 4.4**

    For all finite paginated EC2 response sets, supported filter
    combinations, and supported field selections, the EC2InventoryCollector
    produces output that matches a simple reference model.
    """
    pages, filters, requested_fields = scenario

    # Build parameters
    parameters: dict[str, Any] = {}
    if filters:
        parameters["filters"] = filters
    if requested_fields is not None:
        parameters["fields"] = requested_fields

    # Run the collector
    collector = EC2InventoryCollector()
    session = _make_mock_session(pages)
    outcome = collector.collect(
        "ec2.inventory", "1.0.0", ACCOUNT_ID, REGION, parameters, session
    )

    # Run the reference model
    expected = reference_model(pages, filters, requested_fields, ACCOUNT_ID, REGION)

    # === INVARIANT 6: Status is always "succeeded" when no AWS error occurs ===
    assert outcome.status == "succeeded", (
        f"Expected succeeded status, got {outcome.status}"
    )

    # === INVARIANT 1: Same records ===
    assert len(outcome.records) == len(expected), (
        f"Record count mismatch: collector={len(outcome.records)}, "
        f"reference={len(expected)}"
    )

    # === INVARIANT 2: Same order ===
    for i, (actual_record, expected_record) in enumerate(
        zip(outcome.records, expected)
    ):
        # === INVARIANT 4: Correct resource_identity ===
        assert actual_record.resource_identity == expected_record["resource_identity"], (
            f"Record {i}: resource_identity mismatch: "
            f"actual={actual_record.resource_identity}, "
            f"expected={expected_record['resource_identity']}"
        )

        # === INVARIANT 3: Same fields ===
        actual_fields = dict(actual_record.fields)
        expected_fields = expected_record["fields"]
        assert actual_fields == expected_fields, (
            f"Record {i}: fields mismatch.\n"
            f"  actual={actual_fields}\n"
            f"  expected={expected_fields}"
        )

    # === INVARIANT 5: No duplicate resource_identity values ===
    identities = [r.resource_identity for r in outcome.records]
    assert len(identities) == len(set(identities)), (
        f"Duplicate resource_identity values found: "
        f"{[x for x in identities if identities.count(x) > 1]}"
    )
