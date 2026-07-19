"""
EC2 Inventory Capability Contract — Request Validation and Registration.

Implements:
- EC2 inventory contract constants (capability ID, version, resource type, permissions)
- Parameter validation with StructuredError for unsupported filters/fields (Req 4.5)
- Filter semantics: AND across categories, OR within lists, AND across tag keys (Req 4.3)
- Registration helper without fuzzy routing (Req 4.1, 11.1)

The ec2.inventory@1.0.0 capability declares exactly one AWS operation:
ec2:DescribeInstances. No fuzzy/NLP router exists — agent requests must
provide a fully-qualified capability ID.
"""

from __future__ import annotations

from typing import Any, Mapping

from agentic.interfaces import Collector
from agentic.models import (
    CapabilityDescriptor,
    SemVer,
    StructuredError,
    SchemaViolation,
)
from agentic.registry import CapabilityRegistryImpl


# ---------------------------------------------------------------------------
# Contract Constants
# ---------------------------------------------------------------------------

EC2_CAPABILITY_ID = "ec2.inventory"
EC2_CAPABILITY_VERSION = SemVer(1, 0, 0)
EC2_RESOURCE_TYPE = "instance"
EC2_PERMISSION = "ec2:DescribeInstances"
EC2_ALLOWED_OPERATION = "ec2:DescribeInstances"

# Required identity/provenance fields — always included in output (Req 4.4)
EC2_REQUIRED_FIELDS: tuple[str, ...] = (
    "resource_identity",
    "instance_id",
    "account_id",
    "region",
    "provenance",
)

# Optional v1 fields — included when explicitly requested or when no field set is declared
EC2_OPTIONAL_V1_FIELDS: tuple[str, ...] = (
    "instance_type",
    "state",
    "launch_time",
    "platform",
    "architecture",
    "availability_zone",
    "vpc_id",
    "subnet_id",
    "public_ip",
    "ebs_optimized",
    "name",
    "environment",
)

# All known field names (required + optional)
EC2_ALL_KNOWN_FIELDS: frozenset[str] = frozenset(
    EC2_REQUIRED_FIELDS + EC2_OPTIONAL_V1_FIELDS
)

# Supported filter keys (Req 4.3)
EC2_SUPPORTED_FILTERS: frozenset[str] = frozenset((
    "instance_ids",
    "tags",
    "states",
    "vpc_ids",
    "subnet_ids",
    "availability_zones",
))


# ---------------------------------------------------------------------------
# Filter Semantics (Req 4.3)
# ---------------------------------------------------------------------------
#
# Filter semantics for ec2.inventory@1.0.0:
#
# - AND between categories:
#   filters = {instance_ids: [...], states: [...], vpc_ids: [...]}
#   means: instance_ids match AND states match AND vpc_ids match
#
# - OR within each list:
#   states = ["running", "stopped"]
#   means: state is running OR state is stopped
#
# - AND between tag keys:
#   tags = {"env": ["prod", "staging"], "team": ["infra"]}
#   means: (env is prod OR env is staging) AND (team is infra)
#
# - OR within tag values for the same key:
#   tags = {"env": ["prod", "staging"]}
#   means: env is prod OR env is staging


# ---------------------------------------------------------------------------
# Parameter Validation (Req 4.5)
# ---------------------------------------------------------------------------


def validate_ec2_parameters(parameters: Mapping[str, Any]) -> StructuredError | None:
    """
    Validate ec2.inventory request parameters before collection.

    Checks:
    - resource_type is "instance" (if provided)
    - filters contain only supported filter keys
    - fields contain only known optional field names

    Returns StructuredError with code INVALID_PARAMETERS if validation fails,
    None if parameters are valid.

    Args:
        parameters: The parameters mapping from the CapabilityRequest.

    Returns:
        StructuredError if invalid, None if valid.
    """
    violations: list[SchemaViolation] = []

    # Validate resource_type (fixed value "instance" for v1)
    resource_type = parameters.get("resource_type")
    if resource_type is not None and resource_type != EC2_RESOURCE_TYPE:
        violations.append(
            SchemaViolation(
                json_path="$.parameters.resource_type",
                constraint="enum",
                safe_message=(
                    f"Unsupported resource_type '{resource_type}'. "
                    f"ec2.inventory@1.0.0 supports only '{EC2_RESOURCE_TYPE}'."
                ),
            )
        )

    # Validate filters (only supported filter keys allowed)
    filters = parameters.get("filters")
    if filters is not None:
        if not isinstance(filters, Mapping):
            violations.append(
                SchemaViolation(
                    json_path="$.parameters.filters",
                    constraint="type",
                    safe_message="Filters must be a mapping of filter keys to values.",
                )
            )
        else:
            unsupported_filters = set(filters.keys()) - EC2_SUPPORTED_FILTERS
            for key in sorted(unsupported_filters):
                violations.append(
                    SchemaViolation(
                        json_path=f"$.parameters.filters.{key}",
                        constraint="enum",
                        safe_message=(
                            f"Unsupported filter key '{key}'. "
                            f"Supported filters: {sorted(EC2_SUPPORTED_FILTERS)}"
                        ),
                    )
                )

    # Validate fields (only known optional fields allowed)
    fields = parameters.get("fields")
    if fields is not None:
        if not isinstance(fields, (list, tuple)):
            violations.append(
                SchemaViolation(
                    json_path="$.parameters.fields",
                    constraint="type",
                    safe_message="Fields must be a list of field names.",
                )
            )
        else:
            # Fields selection only references optional fields
            unsupported_fields = set(fields) - frozenset(EC2_OPTIONAL_V1_FIELDS)
            for field_name in sorted(unsupported_fields):
                violations.append(
                    SchemaViolation(
                        json_path=f"$.parameters.fields",
                        constraint="enum",
                        safe_message=(
                            f"Unsupported field '{field_name}'. "
                            f"Supported optional fields: {sorted(EC2_OPTIONAL_V1_FIELDS)}"
                        ),
                    )
                )

    if violations:
        return StructuredError(
            schema_id="structured-error",
            schema_version="1.0.0",
            code="INVALID_PARAMETERS",
            category="validation",
            retryable=False,
            safe_message="ec2.inventory parameter validation failed.",
            capability_id=EC2_CAPABILITY_ID,
            violations=tuple(violations),
        )

    return None


# ---------------------------------------------------------------------------
# Registration Helper (Req 4.1, 11.1)
# ---------------------------------------------------------------------------


def register_ec2_inventory(
    registry: CapabilityRegistryImpl, collector: Collector
) -> None:
    """
    Register the ec2.inventory@1.0.0 capability to the registry.

    Creates the CapabilityDescriptor with correct permissions, allowed
    operations, and schema references. Registers without fuzzy routing —
    agent requests must provide the full capability ID "ec2.inventory"
    (Req 11.1). No implicit service selection or alias resolution occurs.

    Args:
        registry: The capability registry to register into.
        collector: The EC2 inventory collector implementation.

    Raises:
        RegistrationError: If registration validation fails.
    """
    descriptor = CapabilityDescriptor(
        schema_id="capability-descriptor",
        schema_version="1.0.0",
        capability_id=EC2_CAPABILITY_ID,
        version=EC2_CAPABILITY_VERSION,
        input_schema_ref="ec2-inventory-input/1.0.0",
        output_schema_ref="ec2-inventory-output/1.0.0",
        error_schema_ref="structured-error/1.0.0",
        permissions=(EC2_PERMISSION,),
        allowed_operations=(EC2_ALLOWED_OPERATION,),
        prerequisites=(),
        support_status="active",
    )
    registry.register(descriptor, collector)
