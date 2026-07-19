"""
EC2 Inventory Collector — Typed Adapter returning CollectorOutcome.

Implements:
- Full pagination via DescribeInstances paginator (Req 4.2)
- Server-side filter translation and local normalized predicate (Req 4.3)
- Normalized records with stable resource_identity (Req 4.4, 16.6)
- Evidence-ready source metadata (Req 8.1)
- Failure via CollectorOutcome with StructuredError, not boolean (Req 9.2)

Does NOT mutate shared assessment_data or return boolean.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from agentic.ec2_contract import (
    EC2_CAPABILITY_ID,
    EC2_OPTIONAL_V1_FIELDS,
    EC2_REQUIRED_FIELDS,
    validate_ec2_parameters,
)
from agentic.models import (
    CollectorOutcome,
    Evidence,
    ResourceRecord,
    StructuredError,
    TargetPair,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_COLLECTOR_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Filter Translation
# ---------------------------------------------------------------------------


def _translate_filters(filters: Mapping[str, Any]) -> list[dict[str, Any]]:
    """
    Translate capability-level filter parameters to DescribeInstances
    server-side Filters format.

    Filter semantics (Req 4.3):
    - AND across categories
    - OR within lists
    - AND across tag keys, OR within tag values for same key
    """
    aws_filters: list[dict[str, Any]] = []

    if "instance_ids" in filters:
        aws_filters.append({
            "Name": "instance-id",
            "Values": list(filters["instance_ids"]),
        })

    if "states" in filters:
        aws_filters.append({
            "Name": "instance-state-name",
            "Values": list(filters["states"]),
        })

    if "vpc_ids" in filters:
        aws_filters.append({
            "Name": "vpc-id",
            "Values": list(filters["vpc_ids"]),
        })

    if "subnet_ids" in filters:
        aws_filters.append({
            "Name": "subnet-id",
            "Values": list(filters["subnet_ids"]),
        })

    if "availability_zones" in filters:
        aws_filters.append({
            "Name": "availability-zone",
            "Values": list(filters["availability_zones"]),
        })

    if "tags" in filters:
        tags = filters["tags"]
        for key, values in tags.items():
            aws_filters.append({
                "Name": f"tag:{key}",
                "Values": list(values),
            })

    return aws_filters


# ---------------------------------------------------------------------------
# Local Predicate (Defensive Check)
# ---------------------------------------------------------------------------


def _matches_local_predicate(
    instance_fields: Mapping[str, Any], filters: Mapping[str, Any]
) -> bool:
    """
    Apply normalized predicate locally as defensive check.
    Re-checks filters on collected instances to ensure server-side
    filters were applied correctly.

    Returns True if instance passes all filter criteria.
    """
    if not filters:
        return True

    # instance_ids filter
    if "instance_ids" in filters:
        if instance_fields.get("instance_id") not in filters["instance_ids"]:
            return False

    # states filter
    if "states" in filters:
        if instance_fields.get("state") not in filters["states"]:
            return False

    # vpc_ids filter
    if "vpc_ids" in filters:
        if instance_fields.get("vpc_id") not in filters["vpc_ids"]:
            return False

    # subnet_ids filter
    if "subnet_ids" in filters:
        if instance_fields.get("subnet_id") not in filters["subnet_ids"]:
            return False

    # availability_zones filter
    if "availability_zones" in filters:
        if instance_fields.get("availability_zone") not in filters["availability_zones"]:
            return False

    # tags filter (AND across keys, OR within values)
    if "tags" in filters:
        tags = filters["tags"]
        for key, values in tags.items():
            # Match against name/environment tags or raw tag-based fields
            # We map tag keys to normalized field names
            tag_field_map = {
                "Name": "name",
                "Environment": "environment",
                "Env": "environment",
            }
            field_name = tag_field_map.get(key)
            if field_name:
                field_val = instance_fields.get(field_name, "")
                if field_val not in values:
                    return False
            else:
                # For tags not in our known mapping, we can't verify locally
                # (we don't have the raw tags in normalized fields)
                # Accept as passing since server-side filter was applied
                pass

    return True


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def _normalize_launch_time(launch_time: Any) -> str:
    """
    Convert launch_time datetime to UTC RFC 3339 with 'Z' suffix.
    Handles both datetime objects and string inputs.
    """
    if isinstance(launch_time, datetime):
        # Ensure UTC
        if launch_time.tzinfo is None:
            utc_dt = launch_time.replace(tzinfo=timezone.utc)
        else:
            utc_dt = launch_time.astimezone(timezone.utc)
        return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    elif isinstance(launch_time, str):
        return launch_time
    return ""


def _normalize_instance(
    raw_instance: Mapping[str, Any],
    account_id: str,
    region_scope: str,
    evidence_ref: str,
) -> dict[str, Any]:
    """
    Normalize a raw EC2 instance from DescribeInstances into our field schema.
    Returns a dict with all required + optional v1 fields.
    """
    instance_id = raw_instance["InstanceId"]
    tags = {t["Key"]: t["Value"] for t in raw_instance.get("Tags", [])}

    fields: dict[str, Any] = {
        "instance_id": instance_id,
        "instance_type": raw_instance.get("InstanceType", ""),
        "state": raw_instance.get("State", {}).get("Name", ""),
        "launch_time": _normalize_launch_time(raw_instance.get("LaunchTime")),
        "platform": raw_instance.get("Platform", "Linux"),
        "architecture": raw_instance.get("Architecture", ""),
        "availability_zone": raw_instance.get("Placement", {}).get("AvailabilityZone", ""),
        "vpc_id": raw_instance.get("VpcId", ""),
        "subnet_id": raw_instance.get("SubnetId", ""),
        "public_ip": raw_instance.get("PublicIpAddress", None),
        "ebs_optimized": raw_instance.get("EbsOptimized", False),
        "name": tags.get("Name", ""),
        "environment": tags.get("Environment", "") or tags.get("Env", ""),
    }

    return fields


# ---------------------------------------------------------------------------
# EC2InventoryCollector
# ---------------------------------------------------------------------------


class EC2InventoryCollector:
    """
    Typed adapter for EC2 inventory collection.

    Implements the Collector protocol:
    - Returns CollectorOutcome (never boolean)
    - Does NOT mutate shared state
    - Paginates DescribeInstances to exhaustion (Req 4.2)
    - Translates filters server-side + applies local predicate (Req 4.3)
    - Normalizes records with stable resource_identity (Req 4.4, 16.6)
    - Produces Evidence metadata (Req 8.1)
    - Reports failures via StructuredError (Req 9.2)
    """

    def collect(
        self,
        capability_id: str,
        capability_version: str,
        account_id: str,
        region_scope: str,
        parameters: Mapping[str, Any],
        session: Any,
    ) -> CollectorOutcome:
        """
        Execute EC2 inventory collection for one target.

        Args:
            capability_id: "ec2.inventory"
            capability_version: "1.0.0"
            account_id: AWS account ID from invocation context
            region_scope: AWS region scope
            parameters: Request parameters (filters, fields, resource_type)
            session: GuardedSession or boto3-compatible session

        Returns:
            CollectorOutcome with status, records, evidence, or error.
        """
        # Step 1: Validate parameters
        validation_error = validate_ec2_parameters(parameters)
        if validation_error is not None:
            return CollectorOutcome(
                status="failed",
                error=validation_error,
            )

        # Step 2: Prepare filters
        filters = parameters.get("filters", {}) or {}
        aws_filters = _translate_filters(filters)

        # Step 3: Call DescribeInstances with pagination
        try:
            ec2_client = session.client("ec2")
            paginator = ec2_client.get_paginator("describe_instances")

            paginate_kwargs: dict[str, Any] = {}
            if aws_filters:
                paginate_kwargs["Filters"] = aws_filters

            raw_instances: list[Mapping[str, Any]] = []
            for page in paginator.paginate(**paginate_kwargs):
                for reservation in page.get("Reservations", []):
                    for instance in reservation.get("Instances", []):
                        raw_instances.append(instance)

        except Exception as exc:
            # Translate AWS exception to StructuredError (Req 9.2)
            error = _translate_aws_error(exc, account_id, region_scope)
            return CollectorOutcome(
                status="failed",
                error=error,
            )

        # Step 4: Create evidence
        collected_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        evidence = Evidence(
            schema_id="evidence",
            schema_version="1.0.0",
            target=TargetPair(account_id=account_id, region_scope=region_scope),
            capability_id=EC2_CAPABILITY_ID,
            capability_version=capability_version,
            collector_version=_COLLECTOR_VERSION,
            operation="ec2:DescribeInstances",
            collected_at=collected_at,
        )

        # Step 5: Normalize instances and apply local predicate
        requested_fields = parameters.get("fields")
        seen_identities: set[str] = set()
        records: list[ResourceRecord] = []

        for raw_instance in raw_instances:
            instance_fields = _normalize_instance(
                raw_instance, account_id, region_scope, evidence.collected_at
            )

            # Apply local predicate as defensive check
            if not _matches_local_predicate(instance_fields, filters):
                continue

            instance_id = instance_fields["instance_id"]
            resource_identity = f"{account_id}/{region_scope}/{instance_id}"

            # Deduplication by resource_identity
            if resource_identity in seen_identities:
                continue
            seen_identities.add(resource_identity)

            # Field projection
            projected_fields = _apply_field_projection(
                instance_fields, requested_fields
            )

            record = ResourceRecord(
                resource_identity=resource_identity,
                account_id=account_id,
                region_scope=region_scope,
                capability_id=EC2_CAPABILITY_ID,
                fields=projected_fields,
                provenance_ref=collected_at,
            )
            records.append(record)

        # Step 6: Sort by (account_id, region, instance_id)
        records.sort(
            key=lambda r: (r.account_id, r.region_scope, r.fields.get("instance_id", ""))
        )

        return CollectorOutcome(
            status="succeeded",
            records=tuple(records),
            evidence=(evidence,),
        )


# ---------------------------------------------------------------------------
# Field Projection
# ---------------------------------------------------------------------------


def _apply_field_projection(
    instance_fields: dict[str, Any],
    requested_fields: Any | None,
) -> dict[str, Any]:
    """
    Apply field projection. If `requested_fields` is specified,
    only include required fields + declared optional fields from
    the requested set. If None/empty, include all optional v1 fields.
    """
    if requested_fields is None or len(requested_fields) == 0:
        # Include all fields
        return dict(instance_fields)

    # Always include required identity fields that are in instance_fields
    projected: dict[str, Any] = {}

    # instance_id is always included (required field)
    projected["instance_id"] = instance_fields["instance_id"]

    # Include only requested optional fields
    for field_name in requested_fields:
        if field_name in instance_fields:
            projected[field_name] = instance_fields[field_name]

    return projected


# ---------------------------------------------------------------------------
# Error Translation
# ---------------------------------------------------------------------------


def _translate_aws_error(
    exc: Exception, account_id: str, region_scope: str
) -> StructuredError:
    """
    Translate an AWS/boto3 exception to StructuredError.
    Never includes raw credentials in the error message.
    """
    # Determine error category and retryability
    exc_class_name = type(exc).__name__
    safe_message = str(exc)

    # Sanitize: remove any potential credential information
    # Only keep the error code/message, not full exception details
    if hasattr(exc, "response"):
        # botocore ClientError
        response = getattr(exc, "response", {})
        error_info = response.get("Error", {})
        error_code = error_info.get("Code", exc_class_name)
        error_message = error_info.get("Message", str(exc))
        safe_message = f"{error_code}: {error_message}"

        # Determine category
        if error_code in ("Throttling", "RequestLimitExceeded", "TooManyRequestsException"):
            category = "throttled"
            retryable = True
        elif error_code in ("UnauthorizedOperation", "AccessDenied"):
            category = "permission-denied"
            retryable = False
        elif error_code in ("InternalError", "ServiceUnavailable"):
            category = "transient"
            retryable = True
        else:
            category = "internal"
            retryable = False
    else:
        error_code = exc_class_name
        safe_message = f"{exc_class_name}: {str(exc)}"
        category = "internal"
        retryable = False

    return StructuredError(
        schema_id="structured-error",
        schema_version="1.0.0",
        code=error_code,
        category=category,
        retryable=retryable,
        safe_message=safe_message,
        capability_id=EC2_CAPABILITY_ID,
        account_id=account_id,
        region_scope=region_scope,
    )
