"""
Foundation Contract / Snapshot Tests.

Verifies the agentic foundation as a whole behaves correctly when
components interact — schema catalog, processor, and capability registry.

Covers:
- All required schema IDs available with version 1.0.0 (Req 3.1)
- Unsupported version returns supported versions (Req 2.5)
- Duplicate registration is atomic (Req 1.2)
- Manifest does not change without version update (Req 1.3)
- ec2.inventory@1.0.0 full registration with complete declarations (Req 4.1)
- Schema version compatibility (Req 3.6)
"""

from __future__ import annotations

from typing import Any, Mapping

import pytest

from agentic.models import (
    CapabilityDescriptor,
    CapabilityManifest,
    CollectorOutcome,
    SemVer,
    StructuredError,
)
from agentic.registry import (
    CapabilityRegistryImpl,
    DuplicateCapabilityError,
    RegisteredCapability,
)
from agentic.schemas.catalog import SchemaCatalog
from agentic.schemas.processor import CanonicalSchemaProcessor


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


class FakeCollector:
    """A minimal Collector for testing."""

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
def catalog() -> SchemaCatalog:
    return SchemaCatalog()


@pytest.fixture
def processor() -> CanonicalSchemaProcessor:
    return CanonicalSchemaProcessor()


@pytest.fixture
def registry() -> CapabilityRegistryImpl:
    return CapabilityRegistryImpl()


@pytest.fixture
def collector() -> FakeCollector:
    return FakeCollector()


# ---------------------------------------------------------------------------
# 1. All required schema IDs are available (Req 3.1)
# ---------------------------------------------------------------------------

REQUIRED_SCHEMA_IDS = [
    "invocation-request",
    "invocation-result",
    "structured-error",
    "evidence",
    "capability-manifest",
    "assessment-profile",
    "completeness-report",
    "drift-report",
]


class TestRequiredSchemaIDs:
    """All required schema IDs must be available with version 1.0.0."""

    @pytest.mark.parametrize("schema_id", REQUIRED_SCHEMA_IDS)
    def test_schema_id_has_version_1_0_0(self, catalog: SchemaCatalog, schema_id: str):
        """Each required schema ID must have version '1.0.0' available."""
        assert catalog.has_schema(schema_id, "1.0.0"), (
            f"Schema '{schema_id}' version '1.0.0' is not available in the catalog"
        )

    @pytest.mark.parametrize("schema_id", REQUIRED_SCHEMA_IDS)
    def test_schema_id_loads_without_error(self, catalog: SchemaCatalog, schema_id: str):
        """Each required schema loads and returns a non-empty dict."""
        schema = catalog.get_schema(schema_id, "1.0.0")
        assert isinstance(schema, dict)
        assert len(schema) > 0

    def test_all_required_schemas_present_in_supported_list(self, catalog: SchemaCatalog):
        """Every required schema ID appears in supported_schemas()."""
        supported = catalog.supported_schemas()
        for schema_id in REQUIRED_SCHEMA_IDS:
            assert schema_id in supported, (
                f"Schema '{schema_id}' missing from supported_schemas()"
            )
            assert "1.0.0" in supported[schema_id], (
                f"Version '1.0.0' missing for schema '{schema_id}'"
            )


# ---------------------------------------------------------------------------
# 2. Unsupported version returns supported versions (Req 2.5)
# ---------------------------------------------------------------------------


class TestUnsupportedVersionError:
    """Requesting unsupported version produces error listing supported versions."""

    @pytest.mark.parametrize("schema_id", REQUIRED_SCHEMA_IDS)
    def test_unsupported_schema_version_raises_with_supported_list(
        self, catalog: SchemaCatalog, schema_id: str
    ):
        """Requesting version '99.0.0' raises ValueError with supported versions."""
        with pytest.raises(ValueError) as exc_info:
            catalog.get_schema(schema_id, "99.0.0")
        error_msg = str(exc_info.value)
        assert "1.0.0" in error_msg, (
            f"Error for '{schema_id}' should list supported version '1.0.0'"
        )

    @pytest.mark.parametrize("schema_id", REQUIRED_SCHEMA_IDS)
    def test_make_unsupported_error_includes_supported_versions(
        self, catalog: SchemaCatalog, schema_id: str
    ):
        """make_unsupported_error for '99.0.0' includes supported versions."""
        error = catalog.make_unsupported_error(schema_id, "99.0.0")
        assert isinstance(error, StructuredError)
        assert error.code == "UNSUPPORTED_SCHEMA_VERSION"
        assert error.category == "unsupported"
        assert error.retryable is False
        assert "1.0.0" in error.safe_message


# ---------------------------------------------------------------------------
# 3. Duplicate registration is atomic (Req 1.2)
# ---------------------------------------------------------------------------


class TestDuplicateRegistrationAtomic:
    """After a failed duplicate registration, original remains intact."""

    def test_original_intact_after_duplicate_attempt(
        self, registry: CapabilityRegistryImpl, collector: FakeCollector
    ):
        """Failed duplicate registration does not corrupt the original entry."""
        original_desc = CapabilityDescriptor(
            capability_id="ec2.inventory",
            version=SemVer(1, 0, 0),
            input_schema_ref="ec2-inventory-input/1.0.0",
            output_schema_ref="ec2-inventory-output/1.0.0",
            error_schema_ref="structured-error/1.0.0",
            permissions=("ec2:DescribeInstances",),
            allowed_operations=("ec2:DescribeInstances",),
            support_status="active",
        )
        registry.register(original_desc, collector)

        # Attempt duplicate registration (same capability_id, same major)
        duplicate_desc = CapabilityDescriptor(
            capability_id="ec2.inventory",
            version=SemVer(1, 1, 0),
            input_schema_ref="different-input/2.0.0",
            output_schema_ref="different-output/2.0.0",
            error_schema_ref="structured-error/1.0.0",
            permissions=("ec2:DescribeInstances", "ec2:DescribeRegions"),
            allowed_operations=("ec2:DescribeInstances", "ec2:DescribeRegions"),
            support_status="active",
        )

        with pytest.raises(DuplicateCapabilityError):
            registry.register(duplicate_desc, collector)

        # Original must still be intact
        result = registry.resolve("ec2.inventory", "1.0.0")
        assert isinstance(result, RegisteredCapability)
        assert result.descriptor is original_desc
        assert result.descriptor.version == SemVer(1, 0, 0)
        assert result.descriptor.input_schema_ref == "ec2-inventory-input/1.0.0"

    def test_registry_state_not_partially_modified(
        self, registry: CapabilityRegistryImpl, collector: FakeCollector
    ):
        """Registry snapshot is unchanged after failed duplicate registration."""
        desc = CapabilityDescriptor(
            capability_id="s3.inventory",
            version=SemVer(1, 0, 0),
            input_schema_ref="s3-input/1.0.0",
            output_schema_ref="s3-output/1.0.0",
            error_schema_ref="structured-error/1.0.0",
            permissions=("s3:ListBuckets",),
            allowed_operations=("s3:ListBuckets",),
            support_status="active",
        )
        registry.register(desc, collector)
        snapshot_before = registry.snapshot()

        # Attempt duplicate
        dup_desc = CapabilityDescriptor(
            capability_id="s3.inventory",
            version=SemVer(1, 2, 0),
            input_schema_ref="s3-input-v2/1.0.0",
            output_schema_ref="s3-output-v2/1.0.0",
            error_schema_ref="structured-error/1.0.0",
            permissions=("s3:ListBuckets", "s3:GetBucketLocation"),
            allowed_operations=("s3:ListBuckets", "s3:GetBucketLocation"),
            support_status="active",
        )

        with pytest.raises(DuplicateCapabilityError):
            registry.register(dup_desc, collector)

        # Snapshot after failed attempt should be equivalent
        snapshot_after = registry.snapshot()
        assert snapshot_after.manifest_digest == snapshot_before.manifest_digest
        assert len(snapshot_after.capabilities) == len(snapshot_before.capabilities)


# ---------------------------------------------------------------------------
# 4. Manifest does not change without version update (Req 1.3)
# ---------------------------------------------------------------------------


class TestManifestStability:
    """Manifest does not change without new registrations."""

    def test_repeated_snapshot_returns_same_digest(
        self, registry: CapabilityRegistryImpl, collector: FakeCollector
    ):
        """Calling snapshot() repeatedly returns the same digest."""
        desc = CapabilityDescriptor(
            capability_id="ec2.inventory",
            version=SemVer(1, 0, 0),
            input_schema_ref="ec2-inventory-input/1.0.0",
            output_schema_ref="ec2-inventory-output/1.0.0",
            error_schema_ref="structured-error/1.0.0",
            permissions=("ec2:DescribeInstances",),
            allowed_operations=("ec2:DescribeInstances",),
            support_status="active",
        )
        registry.register(desc, collector)

        snap1 = registry.snapshot()
        snap2 = registry.snapshot()
        snap3 = registry.snapshot()

        assert snap1.manifest_digest == snap2.manifest_digest
        assert snap2.manifest_digest == snap3.manifest_digest

    def test_repeated_snapshot_returns_same_reference(
        self, registry: CapabilityRegistryImpl, collector: FakeCollector
    ):
        """Calling snapshot() repeatedly returns the same cached object."""
        desc = CapabilityDescriptor(
            capability_id="iam.users",
            version=SemVer(1, 0, 0),
            input_schema_ref="iam-input/1.0.0",
            output_schema_ref="iam-output/1.0.0",
            error_schema_ref="structured-error/1.0.0",
            permissions=("iam:ListUsers",),
            allowed_operations=("iam:ListUsers",),
            support_status="active",
        )
        registry.register(desc, collector)

        snap1 = registry.snapshot()
        snap2 = registry.snapshot()

        assert snap1 is snap2, "snapshot() should return cached reference"


# ---------------------------------------------------------------------------
# 5. ec2.inventory@1.0.0 full registration (Req 4.1)
# ---------------------------------------------------------------------------


class TestEC2InventoryFullRegistration:
    """ec2.inventory@1.0.0 can be registered with complete declarations."""

    def _register_ec2_inventory(
        self, registry: CapabilityRegistryImpl, collector: FakeCollector
    ) -> CapabilityDescriptor:
        """Register ec2.inventory with full declarations and return descriptor."""
        desc = CapabilityDescriptor(
            capability_id="ec2.inventory",
            version=SemVer(1, 0, 0),
            input_schema_ref="ec2-inventory-input/1.0.0",
            output_schema_ref="ec2-inventory-output/1.0.0",
            error_schema_ref="structured-error/1.0.0",
            permissions=("ec2:DescribeInstances",),
            allowed_operations=("ec2:DescribeInstances",),
            support_status="active",
        )
        registry.register(desc, collector)
        return desc

    def test_resolves_correctly(
        self, registry: CapabilityRegistryImpl, collector: FakeCollector
    ):
        """ec2.inventory@1.0.0 resolves to the correct registered entry."""
        desc = self._register_ec2_inventory(registry, collector)

        result = registry.resolve("ec2.inventory", "1.0.0")
        assert isinstance(result, RegisteredCapability)
        assert result.descriptor == desc
        assert result.descriptor.capability_id == "ec2.inventory"
        assert result.descriptor.version == SemVer(1, 0, 0)

    def test_appears_in_manifest(
        self, registry: CapabilityRegistryImpl, collector: FakeCollector
    ):
        """ec2.inventory@1.0.0 appears in the manifest snapshot."""
        self._register_ec2_inventory(registry, collector)

        manifest = registry.snapshot()
        cap_ids = [c.capability_id for c in manifest.capabilities]
        assert "ec2.inventory" in cap_ids

    def test_manifest_contains_full_schema_refs(
        self, registry: CapabilityRegistryImpl, collector: FakeCollector
    ):
        """Manifest entry contains complete schema refs."""
        self._register_ec2_inventory(registry, collector)

        manifest = registry.snapshot()
        cap = next(
            c for c in manifest.capabilities if c.capability_id == "ec2.inventory"
        )
        assert cap.input_schema_ref == "ec2-inventory-input/1.0.0"
        assert cap.output_schema_ref == "ec2-inventory-output/1.0.0"
        assert cap.error_schema_ref == "structured-error/1.0.0"

    def test_manifest_contains_permissions(
        self, registry: CapabilityRegistryImpl, collector: FakeCollector
    ):
        """Manifest entry contains the declared permissions."""
        self._register_ec2_inventory(registry, collector)

        manifest = registry.snapshot()
        cap = next(
            c for c in manifest.capabilities if c.capability_id == "ec2.inventory"
        )
        assert cap.permissions == ("ec2:DescribeInstances",)

    def test_manifest_contains_allowlist(
        self, registry: CapabilityRegistryImpl, collector: FakeCollector
    ):
        """Manifest entry contains the allowed_operations (allowlist)."""
        self._register_ec2_inventory(registry, collector)

        manifest = registry.snapshot()
        cap = next(
            c for c in manifest.capabilities if c.capability_id == "ec2.inventory"
        )
        assert cap.allowed_operations == ("ec2:DescribeInstances",)

    def test_handler_is_collector(
        self, registry: CapabilityRegistryImpl, collector: FakeCollector
    ):
        """The handler bound to ec2.inventory is the FakeCollector."""
        self._register_ec2_inventory(registry, collector)

        result = registry.resolve("ec2.inventory", "1.0.0")
        assert isinstance(result, RegisteredCapability)
        assert result.handler is collector
        assert hasattr(result.handler, "collect")


# ---------------------------------------------------------------------------
# 6. Schema version compatibility (Req 3.6)
# ---------------------------------------------------------------------------


class TestSchemaVersionCompatibility:
    """Schema version compatibility checks via the processor."""

    def test_same_major_is_compatible(self, processor: CanonicalSchemaProcessor):
        """Same major version (1.0.0 -> 1.2.0) is compatible."""
        # Use any schema_id that exists in the catalog
        assert processor.check_version_compatibility(
            "invocation-request", "1.0.0", "1.2.0"
        ) is True

    def test_different_major_is_incompatible(self, processor: CanonicalSchemaProcessor):
        """Different major version (1.0.0 -> 2.0.0) is incompatible."""
        assert processor.check_version_compatibility(
            "invocation-request", "1.0.0", "2.0.0"
        ) is False

    def test_same_version_is_compatible(self, processor: CanonicalSchemaProcessor):
        """Same exact version (1.0.0 -> 1.0.0) is compatible."""
        assert processor.check_version_compatibility(
            "structured-error", "1.0.0", "1.0.0"
        ) is True

    def test_minor_patch_changes_within_major_compatible(
        self, processor: CanonicalSchemaProcessor
    ):
        """Minor and patch changes within same major are compatible."""
        assert processor.check_version_compatibility(
            "evidence", "1.0.0", "1.99.99"
        ) is True

    def test_catalog_check_major_compatibility_directly(self, catalog: SchemaCatalog):
        """SchemaCatalog.check_major_compatibility matches processor behavior."""
        assert catalog.check_major_compatibility(
            "drift-report", "1.0.0", "1.5.0"
        ) is True
        assert catalog.check_major_compatibility(
            "drift-report", "1.0.0", "2.0.0"
        ) is False
