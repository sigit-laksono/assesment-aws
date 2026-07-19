"""
Tests for EC2 Inventory Capability Contract.

Covers:
- Valid parameters pass validation
- Unsupported filter key returns StructuredError (Req 4.5)
- Unsupported field name returns StructuredError (Req 4.5)
- Invalid resource_type returns StructuredError
- Registration creates discoverable capability with correct permissions/operations/version (Req 4.1, 11.1)
- No fuzzy/implicit routing — requesting "ec2" without ".inventory" returns unsupported (Req 11.1)
"""

from __future__ import annotations

from typing import Any, Mapping

import pytest

from agentic.ec2_contract import (
    EC2_ALLOWED_OPERATION,
    EC2_CAPABILITY_ID,
    EC2_CAPABILITY_VERSION,
    EC2_OPTIONAL_V1_FIELDS,
    EC2_PERMISSION,
    EC2_REQUIRED_FIELDS,
    EC2_RESOURCE_TYPE,
    EC2_SUPPORTED_FILTERS,
    register_ec2_inventory,
    validate_ec2_parameters,
)
from agentic.models import (
    CollectorOutcome,
    SemVer,
    StructuredError,
)
from agentic.registry import CapabilityRegistryImpl, RegisteredCapability


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


class FakeEC2Collector:
    """A minimal Collector for testing ec2.inventory registration."""

    def collect(
        self,
        capability_id: str,
        capability_version: str,
        account_id: str,
        region_scope: str,
        parameters: Mapping[str, Any],
        session: Any,
    ) -> CollectorOutcome:
        return CollectorOutcome(status="succeeded", records=(), evidence=())


@pytest.fixture
def registry() -> CapabilityRegistryImpl:
    return CapabilityRegistryImpl()


@pytest.fixture
def collector() -> FakeEC2Collector:
    return FakeEC2Collector()


# ---------------------------------------------------------------------------
# Contract Constants
# ---------------------------------------------------------------------------


class TestEC2ContractConstants:
    """Verify contract constants are correctly defined."""

    def test_capability_id(self):
        assert EC2_CAPABILITY_ID == "ec2.inventory"

    def test_capability_version(self):
        assert EC2_CAPABILITY_VERSION == SemVer(1, 0, 0)

    def test_resource_type(self):
        assert EC2_RESOURCE_TYPE == "instance"

    def test_permission(self):
        assert EC2_PERMISSION == "ec2:DescribeInstances"

    def test_allowed_operation(self):
        assert EC2_ALLOWED_OPERATION == "ec2:DescribeInstances"

    def test_required_fields_present(self):
        expected = {"resource_identity", "instance_id", "account_id", "region", "provenance"}
        assert set(EC2_REQUIRED_FIELDS) == expected

    def test_optional_v1_fields_present(self):
        expected = {
            "instance_type", "state", "launch_time", "platform",
            "architecture", "availability_zone", "vpc_id", "subnet_id",
            "public_ip", "ebs_optimized", "name", "environment",
        }
        assert set(EC2_OPTIONAL_V1_FIELDS) == expected

    def test_supported_filters(self):
        expected = {
            "instance_ids", "tags", "states", "vpc_ids",
            "subnet_ids", "availability_zones",
        }
        assert set(EC2_SUPPORTED_FILTERS) == expected


# ---------------------------------------------------------------------------
# Parameter Validation — Valid Cases
# ---------------------------------------------------------------------------


class TestValidParameters:
    """Valid parameters pass validation without error."""

    def test_empty_parameters(self):
        """Empty parameters are valid (no filters, no field selection)."""
        result = validate_ec2_parameters({})
        assert result is None

    def test_resource_type_instance(self):
        """Explicit resource_type='instance' is valid."""
        result = validate_ec2_parameters({"resource_type": "instance"})
        assert result is None

    def test_valid_filters_states(self):
        """Valid filter with states list."""
        result = validate_ec2_parameters({
            "filters": {"states": ["running", "stopped"]}
        })
        assert result is None

    def test_valid_filters_instance_ids(self):
        """Valid filter with instance_ids list."""
        result = validate_ec2_parameters({
            "filters": {"instance_ids": ["i-abc123", "i-def456"]}
        })
        assert result is None

    def test_valid_filters_tags(self):
        """Valid filter with tags mapping (AND across keys, OR within values)."""
        result = validate_ec2_parameters({
            "filters": {"tags": {"env": ["prod", "staging"], "team": ["infra"]}}
        })
        assert result is None

    def test_valid_filters_multiple_categories(self):
        """Valid multiple filter categories (AND semantics across categories)."""
        result = validate_ec2_parameters({
            "filters": {
                "states": ["running"],
                "vpc_ids": ["vpc-123"],
                "subnet_ids": ["subnet-abc"],
                "availability_zones": ["us-east-1a"],
            }
        })
        assert result is None

    def test_valid_fields_subset(self):
        """Valid field selection with a subset of optional fields."""
        result = validate_ec2_parameters({
            "fields": ["instance_type", "state", "name"]
        })
        assert result is None

    def test_valid_fields_all_optional(self):
        """Valid field selection with all optional fields."""
        result = validate_ec2_parameters({
            "fields": list(EC2_OPTIONAL_V1_FIELDS)
        })
        assert result is None

    def test_valid_combined_parameters(self):
        """Valid combination of resource_type, filters, and fields."""
        result = validate_ec2_parameters({
            "resource_type": "instance",
            "filters": {"states": ["running"]},
            "fields": ["instance_type", "vpc_id"],
        })
        assert result is None


# ---------------------------------------------------------------------------
# Parameter Validation — Unsupported Filter Key (Req 4.5)
# ---------------------------------------------------------------------------


class TestUnsupportedFilterKey:
    """Unsupported filter key returns StructuredError before collection."""

    def test_unsupported_filter_returns_error(self):
        """Unknown filter key triggers INVALID_PARAMETERS error."""
        result = validate_ec2_parameters({
            "filters": {"unknown_filter": ["value"]}
        })
        assert result is not None
        assert isinstance(result, StructuredError)
        assert result.code == "INVALID_PARAMETERS"
        assert result.category == "validation"
        assert result.retryable is False
        assert result.capability_id == EC2_CAPABILITY_ID

    def test_error_mentions_unsupported_key(self):
        """Error violations reference the unsupported filter key."""
        result = validate_ec2_parameters({
            "filters": {"security_groups": ["sg-abc"]}
        })
        assert result is not None
        assert len(result.violations) >= 1
        assert "security_groups" in result.violations[0].safe_message

    def test_multiple_unsupported_filters(self):
        """Multiple unsupported filter keys all appear in violations."""
        result = validate_ec2_parameters({
            "filters": {"bad_filter_1": [], "bad_filter_2": []}
        })
        assert result is not None
        assert len(result.violations) == 2

    def test_mix_valid_and_invalid_filters(self):
        """Valid filters pass but one invalid filter causes error."""
        result = validate_ec2_parameters({
            "filters": {"states": ["running"], "invalid_key": ["x"]}
        })
        assert result is not None
        assert result.code == "INVALID_PARAMETERS"
        # Only the invalid key is a violation
        violation_messages = " ".join(v.safe_message for v in result.violations)
        assert "invalid_key" in violation_messages


# ---------------------------------------------------------------------------
# Parameter Validation — Unsupported Field Name (Req 4.5)
# ---------------------------------------------------------------------------


class TestUnsupportedFieldName:
    """Unsupported field name returns StructuredError before collection."""

    def test_unsupported_field_returns_error(self):
        """Unknown field name triggers INVALID_PARAMETERS error."""
        result = validate_ec2_parameters({
            "fields": ["nonexistent_field"]
        })
        assert result is not None
        assert isinstance(result, StructuredError)
        assert result.code == "INVALID_PARAMETERS"
        assert result.category == "validation"

    def test_error_mentions_unsupported_field(self):
        """Error violations reference the unsupported field name."""
        result = validate_ec2_parameters({
            "fields": ["security_group_ids"]
        })
        assert result is not None
        assert len(result.violations) >= 1
        assert "security_group_ids" in result.violations[0].safe_message

    def test_multiple_unsupported_fields(self):
        """Multiple unsupported fields all appear in violations."""
        result = validate_ec2_parameters({
            "fields": ["field_x", "field_y"]
        })
        assert result is not None
        assert len(result.violations) == 2

    def test_mix_valid_and_invalid_fields(self):
        """Valid fields pass but one invalid field causes error."""
        result = validate_ec2_parameters({
            "fields": ["instance_type", "nonexistent"]
        })
        assert result is not None
        assert result.code == "INVALID_PARAMETERS"
        violation_messages = " ".join(v.safe_message for v in result.violations)
        assert "nonexistent" in violation_messages


# ---------------------------------------------------------------------------
# Parameter Validation — Invalid resource_type
# ---------------------------------------------------------------------------


class TestInvalidResourceType:
    """Invalid resource_type returns StructuredError."""

    def test_wrong_resource_type_returns_error(self):
        """resource_type other than 'instance' triggers error."""
        result = validate_ec2_parameters({"resource_type": "volume"})
        assert result is not None
        assert isinstance(result, StructuredError)
        assert result.code == "INVALID_PARAMETERS"
        assert result.category == "validation"

    def test_error_mentions_unsupported_resource_type(self):
        """Error message references the unsupported resource_type."""
        result = validate_ec2_parameters({"resource_type": "snapshot"})
        assert result is not None
        assert len(result.violations) >= 1
        assert "snapshot" in result.violations[0].safe_message
        assert "instance" in result.violations[0].safe_message


# ---------------------------------------------------------------------------
# Registration Creates Discoverable Capability (Req 4.1, 11.1)
# ---------------------------------------------------------------------------


class TestEC2InventoryRegistration:
    """Registration creates discoverable capability with correct declarations."""

    def test_registration_succeeds(
        self, registry: CapabilityRegistryImpl, collector: FakeEC2Collector
    ):
        """register_ec2_inventory completes without error."""
        register_ec2_inventory(registry, collector)
        # No exception = success

    def test_resolves_by_exact_id_and_version(
        self, registry: CapabilityRegistryImpl, collector: FakeEC2Collector
    ):
        """Registered capability resolves by exact capability ID and version."""
        register_ec2_inventory(registry, collector)

        result = registry.resolve("ec2.inventory", "1.0.0")
        assert isinstance(result, RegisteredCapability)
        assert result.descriptor.capability_id == "ec2.inventory"
        assert result.descriptor.version == SemVer(1, 0, 0)

    def test_correct_permission_declared(
        self, registry: CapabilityRegistryImpl, collector: FakeEC2Collector
    ):
        """Registered capability declares ec2:DescribeInstances permission."""
        register_ec2_inventory(registry, collector)

        result = registry.resolve("ec2.inventory", "1.0.0")
        assert isinstance(result, RegisteredCapability)
        assert result.descriptor.permissions == ("ec2:DescribeInstances",)

    def test_correct_allowed_operations(
        self, registry: CapabilityRegistryImpl, collector: FakeEC2Collector
    ):
        """Registered capability declares exactly one allowed operation (Req 11.1)."""
        register_ec2_inventory(registry, collector)

        result = registry.resolve("ec2.inventory", "1.0.0")
        assert isinstance(result, RegisteredCapability)
        assert result.descriptor.allowed_operations == ("ec2:DescribeInstances",)

    def test_appears_in_manifest(
        self, registry: CapabilityRegistryImpl, collector: FakeEC2Collector
    ):
        """ec2.inventory appears in the capability manifest after registration."""
        register_ec2_inventory(registry, collector)

        manifest = registry.snapshot()
        cap_ids = [c.capability_id for c in manifest.capabilities]
        assert "ec2.inventory" in cap_ids

    def test_handler_is_collector(
        self, registry: CapabilityRegistryImpl, collector: FakeEC2Collector
    ):
        """The handler bound to ec2.inventory is the provided collector."""
        register_ec2_inventory(registry, collector)

        result = registry.resolve("ec2.inventory", "1.0.0")
        assert isinstance(result, RegisteredCapability)
        assert result.handler is collector

    def test_support_status_is_active(
        self, registry: CapabilityRegistryImpl, collector: FakeEC2Collector
    ):
        """Registered capability has active support status."""
        register_ec2_inventory(registry, collector)

        result = registry.resolve("ec2.inventory", "1.0.0")
        assert isinstance(result, RegisteredCapability)
        assert result.descriptor.support_status == "active"


# ---------------------------------------------------------------------------
# No Fuzzy/Implicit Routing (Req 11.1)
# ---------------------------------------------------------------------------


class TestNoFuzzyRouting:
    """Agent requests must provide full capability ID — no fuzzy routing."""

    def test_bare_ec2_returns_unsupported(
        self, registry: CapabilityRegistryImpl, collector: FakeEC2Collector
    ):
        """Requesting "ec2" (without ".inventory") returns unsupported error."""
        register_ec2_inventory(registry, collector)

        result = registry.resolve("ec2", "1.0.0")
        assert isinstance(result, StructuredError)
        assert result.code == "UNSUPPORTED_CAPABILITY"
        assert result.category == "unsupported"

    def test_partial_id_returns_unsupported(
        self, registry: CapabilityRegistryImpl, collector: FakeEC2Collector
    ):
        """Requesting "ec2.inv" (partial) returns unsupported error."""
        register_ec2_inventory(registry, collector)

        result = registry.resolve("ec2.inv", "1.0.0")
        assert isinstance(result, StructuredError)
        assert result.code == "UNSUPPORTED_CAPABILITY"

    def test_case_sensitive_id(
        self, registry: CapabilityRegistryImpl, collector: FakeEC2Collector
    ):
        """Capability ID resolution is case-sensitive."""
        register_ec2_inventory(registry, collector)

        result = registry.resolve("EC2.INVENTORY", "1.0.0")
        assert isinstance(result, StructuredError)
        assert result.code == "UNSUPPORTED_CAPABILITY"

    def test_wrong_version_returns_unsupported(
        self, registry: CapabilityRegistryImpl, collector: FakeEC2Collector
    ):
        """Requesting correct ID but wrong version returns unsupported."""
        register_ec2_inventory(registry, collector)

        result = registry.resolve("ec2.inventory", "2.0.0")
        assert isinstance(result, StructuredError)
        assert result.code == "UNSUPPORTED_CAPABILITY"
