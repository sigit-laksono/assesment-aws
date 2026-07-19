"""
Tests for Planner Target Pair and Region Discovery (Task 5.1).

Covers:
- Normalize/deduplicate/sort account-region scope (Req 6.1)
- Global capabilities use 'aws-global' once per account (Req 6.1)
- Region discovery snapshot persisted before regional collection (Req 6.2)
- Stable execution unit IDs from request digest, capability version,
  target, and ordinal
- Prerequisite unit dependencies validated (global prereq -> regional)
- Mixed global and regional capabilities in same plan
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
    RequiredProfileItem,
    SemVer,
)
from agentic.orchestrator import (
    _build_scope_map,
    _normalize_global_targets,
    _normalize_targets,
    _plan,
    _validate_prerequisite_unit_dependencies,
)
from agentic.registry import CapabilityRegistryImpl, RegisteredCapability
from agentic.schemas.processor import CanonicalSchemaProcessor


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


class FakeCollector:
    """A minimal Collector implementation for testing."""

    def __init__(self, name: str = "fake"):
        self.name = name

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


def _make_request(
    accounts: tuple[AccountTarget, ...],
    regions: tuple[str, ...],
    capabilities: tuple[CapabilityRequest, ...],
) -> InvocationRequest:
    return InvocationRequest(
        schema_id="invocation-request",
        schema_version="1.0.0",
        capabilities=capabilities,
        targets=accounts,
        regions=regions,
        execution_context=ExecutionContext(
            caller_id="agent/test",
            correlation_id="corr-target-pair",
        ),
    )


def _make_registry_global_and_regional() -> CapabilityRegistryImpl:
    """
    Registry with:
    - iam.identity (global, no prereqs)
    - ec2.inventory (regional, prereqs: iam.identity)
    """
    registry = CapabilityRegistryImpl()

    iam_desc = CapabilityDescriptor(
        capability_id="iam.identity",
        version=SemVer(1, 0, 0),
        input_schema_ref="iam/1.0.0",
        output_schema_ref="iam/1.0.0",
        error_schema_ref="structured-error/1.0.0",
        permissions=("sts:GetCallerIdentity",),
        allowed_operations=("sts:GetCallerIdentity",),
        prerequisites=(),
        scope="global",
    )
    registry.register(iam_desc, FakeCollector("iam"))

    ec2_desc = CapabilityDescriptor(
        capability_id="ec2.inventory",
        version=SemVer(1, 0, 0),
        input_schema_ref="ec2/1.0.0",
        output_schema_ref="ec2/1.0.0",
        error_schema_ref="structured-error/1.0.0",
        permissions=("ec2:DescribeInstances",),
        allowed_operations=("ec2:DescribeInstances",),
        prerequisites=("iam.identity",),
        scope="regional",
    )
    registry.register(ec2_desc, FakeCollector("ec2"))

    return registry


# ---------------------------------------------------------------------------
# Test: _normalize_targets (regional)
# ---------------------------------------------------------------------------


class TestNormalizeTargets:
    """Tests for _normalize_targets (regional scope)."""

    def test_basic_normalization(self):
        """Single account x single region produces one pair."""
        accounts = (AccountTarget(account_id="111111111111"),)
        regions = ("us-east-1",)
        result = _normalize_targets(accounts, regions)
        assert result == [("111111111111", "us-east-1")]

    def test_deduplication(self):
        """Duplicate account-region pairs are deduplicated."""
        accounts = (
            AccountTarget(account_id="111111111111"),
            AccountTarget(account_id="111111111111"),
        )
        regions = ("us-east-1",)
        result = _normalize_targets(accounts, regions)
        assert result == [("111111111111", "us-east-1")]

    def test_lexicographic_sort(self):
        """Result is sorted lexicographically by (account_id, region)."""
        accounts = (
            AccountTarget(account_id="222222222222"),
            AccountTarget(account_id="111111111111"),
        )
        regions = ("us-west-2", "ap-southeast-1")
        result = _normalize_targets(accounts, regions)
        assert result == [
            ("111111111111", "ap-southeast-1"),
            ("111111111111", "us-west-2"),
            ("222222222222", "ap-southeast-1"),
            ("222222222222", "us-west-2"),
        ]

    def test_multiple_accounts_multiple_regions(self):
        """Cross-product of accounts and regions."""
        accounts = (
            AccountTarget(account_id="111111111111"),
            AccountTarget(account_id="222222222222"),
        )
        regions = ("us-east-1", "eu-west-1")
        result = _normalize_targets(accounts, regions)
        assert len(result) == 4


# ---------------------------------------------------------------------------
# Test: _normalize_global_targets
# ---------------------------------------------------------------------------


class TestNormalizeGlobalTargets:
    """Tests for _normalize_global_targets."""

    def test_one_per_account(self):
        """Each unique account gets exactly one 'aws-global' entry."""
        accounts = (
            AccountTarget(account_id="111111111111"),
            AccountTarget(account_id="222222222222"),
        )
        result = _normalize_global_targets(accounts)
        assert result == [
            ("111111111111", "aws-global"),
            ("222222222222", "aws-global"),
        ]

    def test_deduplicate_same_account(self):
        """Duplicate accounts produce only one 'aws-global' entry."""
        accounts = (
            AccountTarget(account_id="111111111111"),
            AccountTarget(account_id="111111111111"),
        )
        result = _normalize_global_targets(accounts)
        assert result == [("111111111111", "aws-global")]

    def test_sorted_output(self):
        """Output is sorted by account_id."""
        accounts = (
            AccountTarget(account_id="999999999999"),
            AccountTarget(account_id="111111111111"),
        )
        result = _normalize_global_targets(accounts)
        assert result[0][0] == "111111111111"
        assert result[1][0] == "999999999999"


# ---------------------------------------------------------------------------
# Test: Global capability planning
# ---------------------------------------------------------------------------


class TestGlobalCapabilityPlanning:
    """Tests for global capability scope in the planner."""

    def test_global_capability_uses_aws_global_scope(self):
        """Global capability creates units with 'aws-global' region_scope."""
        registry = _make_registry_global_and_regional()
        processor = CanonicalSchemaProcessor()

        request = _make_request(
            accounts=(AccountTarget(account_id="111111111111"),),
            regions=("us-east-1", "eu-west-1"),
            capabilities=(
                CapabilityRequest(id="iam.identity", version="1.0.0"),
                CapabilityRequest(id="ec2.inventory", version="1.0.0"),
            ),
        )

        manifest = registry.snapshot()
        plan = _plan(request, manifest, registry, processor)

        # iam.identity is global: 1 account × 1 (aws-global) = 1 unit
        # ec2.inventory is regional: 1 account × 2 regions = 2 units
        iam_units = [u for u in plan.units if u.capability_id == "iam.identity"]
        ec2_units = [u for u in plan.units if u.capability_id == "ec2.inventory"]

        assert len(iam_units) == 1
        assert iam_units[0].region_scope == "aws-global"
        assert iam_units[0].account_id == "111111111111"

        assert len(ec2_units) == 2
        for u in ec2_units:
            assert u.region_scope in ("us-east-1", "eu-west-1")

    def test_global_once_per_account_even_with_multiple_regions(self):
        """Global capability appears once per account regardless of how many regions."""
        registry = _make_registry_global_and_regional()
        processor = CanonicalSchemaProcessor()

        request = _make_request(
            accounts=(
                AccountTarget(account_id="111111111111"),
                AccountTarget(account_id="222222222222"),
            ),
            regions=("us-east-1", "eu-west-1", "ap-southeast-1"),
            capabilities=(
                CapabilityRequest(id="iam.identity", version="1.0.0"),
                CapabilityRequest(id="ec2.inventory", version="1.0.0"),
            ),
        )

        manifest = registry.snapshot()
        plan = _plan(request, manifest, registry, processor)

        iam_units = [u for u in plan.units if u.capability_id == "iam.identity"]
        ec2_units = [u for u in plan.units if u.capability_id == "ec2.inventory"]

        # 2 accounts × 1 global = 2 iam units
        assert len(iam_units) == 2
        for u in iam_units:
            assert u.region_scope == "aws-global"

        # 2 accounts × 3 regions = 6 ec2 units
        assert len(ec2_units) == 6

    def test_global_prerequisite_satisfied_for_regional_unit(self):
        """Regional units reference the global prerequisite unit for the same account."""
        registry = _make_registry_global_and_regional()
        processor = CanonicalSchemaProcessor()

        request = _make_request(
            accounts=(AccountTarget(account_id="111111111111"),),
            regions=("us-east-1",),
            capabilities=(
                CapabilityRequest(id="iam.identity", version="1.0.0"),
                CapabilityRequest(id="ec2.inventory", version="1.0.0"),
            ),
        )

        manifest = registry.snapshot()
        plan = _plan(request, manifest, registry, processor)

        iam_units = [u for u in plan.units if u.capability_id == "iam.identity"]
        ec2_units = [u for u in plan.units if u.capability_id == "ec2.inventory"]

        assert len(iam_units) == 1
        assert len(ec2_units) == 1

        # ec2 regional unit depends on iam global unit
        assert iam_units[0].unit_id in ec2_units[0].prerequisite_unit_ids

    def test_multi_account_global_prereq_correct_account(self):
        """Each regional unit references its OWN account's global prerequisite."""
        registry = _make_registry_global_and_regional()
        processor = CanonicalSchemaProcessor()

        request = _make_request(
            accounts=(
                AccountTarget(account_id="111111111111"),
                AccountTarget(account_id="222222222222"),
            ),
            regions=("us-east-1",),
            capabilities=(
                CapabilityRequest(id="iam.identity", version="1.0.0"),
                CapabilityRequest(id="ec2.inventory", version="1.0.0"),
            ),
        )

        manifest = registry.snapshot()
        plan = _plan(request, manifest, registry, processor)

        iam_units = {
            u.account_id: u
            for u in plan.units
            if u.capability_id == "iam.identity"
        }
        ec2_units = [u for u in plan.units if u.capability_id == "ec2.inventory"]

        for ec2_unit in ec2_units:
            # The ec2 unit should reference the iam unit for the SAME account
            expected_prereq = iam_units[ec2_unit.account_id].unit_id
            assert expected_prereq in ec2_unit.prerequisite_unit_ids


# ---------------------------------------------------------------------------
# Test: Region Discovery Snapshot
# ---------------------------------------------------------------------------


class TestRegionDiscoverySnapshot:
    """Tests for region discovery snapshot persistence (Req 6.2)."""

    def test_discovery_snapshot_persisted(self):
        """Region discovery snapshot is stored in the plan."""
        registry = CapabilityRegistryImpl()
        ec2_desc = CapabilityDescriptor(
            capability_id="ec2.inventory",
            version=SemVer(1, 0, 0),
            input_schema_ref="ec2/1.0.0",
            output_schema_ref="ec2/1.0.0",
            error_schema_ref="structured-error/1.0.0",
            permissions=("ec2:DescribeInstances",),
            allowed_operations=("ec2:DescribeInstances",),
            prerequisites=(),
            scope="regional",
        )
        registry.register(ec2_desc, FakeCollector("ec2"))
        processor = CanonicalSchemaProcessor()

        request = _make_request(
            accounts=(AccountTarget(account_id="111111111111"),),
            regions=("us-east-1", "eu-west-1"),
            capabilities=(
                CapabilityRequest(id="ec2.inventory", version="1.0.0"),
            ),
        )

        discovered = {
            "111111111111": ("us-east-1", "eu-west-1", "ap-southeast-1"),
        }

        manifest = registry.snapshot()
        plan = _plan(
            request, manifest, registry, processor,
            discovered_regions=discovered,
        )

        assert "111111111111" in plan.region_discovery_snapshot
        assert plan.region_discovery_snapshot["111111111111"] == (
            "ap-southeast-1", "eu-west-1", "us-east-1"
        )

    def test_discovery_snapshot_sorted(self):
        """Snapshot keys and values are sorted."""
        registry = CapabilityRegistryImpl()
        ec2_desc = CapabilityDescriptor(
            capability_id="ec2.inventory",
            version=SemVer(1, 0, 0),
            input_schema_ref="ec2/1.0.0",
            output_schema_ref="ec2/1.0.0",
            error_schema_ref="structured-error/1.0.0",
            permissions=("ec2:DescribeInstances",),
            allowed_operations=("ec2:DescribeInstances",),
            prerequisites=(),
            scope="regional",
        )
        registry.register(ec2_desc, FakeCollector("ec2"))
        processor = CanonicalSchemaProcessor()

        request = _make_request(
            accounts=(
                AccountTarget(account_id="222222222222"),
                AccountTarget(account_id="111111111111"),
            ),
            regions=("us-east-1",),
            capabilities=(
                CapabilityRequest(id="ec2.inventory", version="1.0.0"),
            ),
        )

        discovered = {
            "222222222222": ("eu-west-1", "us-east-1"),
            "111111111111": ("us-west-2", "ap-southeast-1"),
        }

        manifest = registry.snapshot()
        plan = _plan(
            request, manifest, registry, processor,
            discovered_regions=discovered,
        )

        # Keys sorted
        keys = list(plan.region_discovery_snapshot.keys())
        assert keys == sorted(keys)

        # Values sorted
        for account_id, regions in plan.region_discovery_snapshot.items():
            assert list(regions) == sorted(regions)

    def test_no_discovery_means_empty_snapshot(self):
        """Without discovered_regions, snapshot is empty."""
        registry = CapabilityRegistryImpl()
        ec2_desc = CapabilityDescriptor(
            capability_id="ec2.inventory",
            version=SemVer(1, 0, 0),
            input_schema_ref="ec2/1.0.0",
            output_schema_ref="ec2/1.0.0",
            error_schema_ref="structured-error/1.0.0",
            permissions=("ec2:DescribeInstances",),
            allowed_operations=("ec2:DescribeInstances",),
            prerequisites=(),
            scope="regional",
        )
        registry.register(ec2_desc, FakeCollector("ec2"))
        processor = CanonicalSchemaProcessor()

        request = _make_request(
            accounts=(AccountTarget(account_id="111111111111"),),
            regions=("us-east-1",),
            capabilities=(
                CapabilityRequest(id="ec2.inventory", version="1.0.0"),
            ),
        )

        manifest = registry.snapshot()
        plan = _plan(request, manifest, registry, processor)

        assert plan.region_discovery_snapshot == {}


# ---------------------------------------------------------------------------
# Test: Stable Unit IDs
# ---------------------------------------------------------------------------


class TestStableUnitIds:
    """Tests for stable unit ID generation with global scope."""

    def test_global_unit_id_is_stable(self):
        """Same inputs produce the same global unit ID."""
        registry = _make_registry_global_and_regional()
        processor = CanonicalSchemaProcessor()

        request = _make_request(
            accounts=(AccountTarget(account_id="111111111111"),),
            regions=("us-east-1",),
            capabilities=(
                CapabilityRequest(id="iam.identity", version="1.0.0"),
                CapabilityRequest(id="ec2.inventory", version="1.0.0"),
            ),
        )

        manifest = registry.snapshot()
        plan1 = _plan(request, manifest, registry, processor)
        plan2 = _plan(request, manifest, registry, processor)

        # All unit IDs should be identical
        for u1, u2 in zip(plan1.units, plan2.units):
            assert u1.unit_id == u2.unit_id

    def test_unit_id_differs_for_different_scope(self):
        """Global and regional scope produce different unit IDs (different region_scope)."""
        registry = _make_registry_global_and_regional()
        processor = CanonicalSchemaProcessor()

        request = _make_request(
            accounts=(AccountTarget(account_id="111111111111"),),
            regions=("us-east-1",),
            capabilities=(
                CapabilityRequest(id="iam.identity", version="1.0.0"),
                CapabilityRequest(id="ec2.inventory", version="1.0.0"),
            ),
        )

        manifest = registry.snapshot()
        plan = _plan(request, manifest, registry, processor)

        unit_ids = [u.unit_id for u in plan.units]
        # All unit IDs are unique
        assert len(unit_ids) == len(set(unit_ids))


# ---------------------------------------------------------------------------
# Test: _build_scope_map
# ---------------------------------------------------------------------------


class TestBuildScopeMap:
    """Tests for _build_scope_map helper."""

    def test_uses_descriptor_scope_by_default(self):
        """Without profile items, scope comes from descriptor."""
        registry = _make_registry_global_and_regional()
        entries = []
        for cap_entries in registry._entries.values():
            for entry in cap_entries.values():
                entries.append(entry)

        scope_map = _build_scope_map(entries, profile_items=None)
        assert scope_map["iam.identity"] == "global"
        assert scope_map["ec2.inventory"] == "regional"

    def test_profile_items_override_descriptor_scope(self):
        """Profile items' target_scope overrides descriptor scope."""
        registry = _make_registry_global_and_regional()
        entries = []
        for cap_entries in registry._entries.values():
            for entry in cap_entries.values():
                entries.append(entry)

        # Profile says ec2 is global (override)
        profile_items = (
            RequiredProfileItem(
                capability_id="ec2.inventory",
                capability_version="1.0.0",
                target_scope="global",
            ),
        )

        scope_map = _build_scope_map(entries, profile_items=profile_items)
        assert scope_map["ec2.inventory"] == "global"
        # iam.identity not in profile items, uses descriptor
        assert scope_map["iam.identity"] == "global"


# ---------------------------------------------------------------------------
# Test: _validate_prerequisite_unit_dependencies
# ---------------------------------------------------------------------------


class TestValidatePrerequisiteDependencies:
    """Tests for prerequisite unit ID validation."""

    def test_valid_dependencies_return_empty(self):
        """Valid plan has no errors."""
        registry = _make_registry_global_and_regional()
        processor = CanonicalSchemaProcessor()

        request = _make_request(
            accounts=(AccountTarget(account_id="111111111111"),),
            regions=("us-east-1",),
            capabilities=(
                CapabilityRequest(id="iam.identity", version="1.0.0"),
                CapabilityRequest(id="ec2.inventory", version="1.0.0"),
            ),
        )

        manifest = registry.snapshot()
        plan = _plan(request, manifest, registry, processor)

        errors = _validate_prerequisite_unit_dependencies(plan.units)
        assert errors == []

    def test_plan_ordinals_sequential(self):
        """Ordinals are sequential starting at 0 for mixed global/regional."""
        registry = _make_registry_global_and_regional()
        processor = CanonicalSchemaProcessor()

        request = _make_request(
            accounts=(
                AccountTarget(account_id="111111111111"),
                AccountTarget(account_id="222222222222"),
            ),
            regions=("us-east-1", "eu-west-1"),
            capabilities=(
                CapabilityRequest(id="iam.identity", version="1.0.0"),
                CapabilityRequest(id="ec2.inventory", version="1.0.0"),
            ),
        )

        manifest = registry.snapshot()
        plan = _plan(request, manifest, registry, processor)

        ordinals = [u.ordinal for u in plan.units]
        assert ordinals == list(range(len(plan.units)))


# ---------------------------------------------------------------------------
# Test: Profile Items Scope Integration
# ---------------------------------------------------------------------------


class TestProfileItemsScopeIntegration:
    """Tests for profile_items integration with the planner."""

    def test_profile_items_determine_scope(self):
        """When profile_items are provided, they determine scope."""
        registry = CapabilityRegistryImpl()

        # Register both capabilities as 'regional' in descriptor
        s3_desc = CapabilityDescriptor(
            capability_id="s3.inventory",
            version=SemVer(1, 0, 0),
            input_schema_ref="s3/1.0.0",
            output_schema_ref="s3/1.0.0",
            error_schema_ref="structured-error/1.0.0",
            permissions=("s3:ListBuckets",),
            allowed_operations=("s3:ListBuckets",),
            prerequisites=(),
            scope="regional",  # descriptor says regional
        )
        registry.register(s3_desc, FakeCollector("s3"))

        processor = CanonicalSchemaProcessor()
        request = _make_request(
            accounts=(AccountTarget(account_id="111111111111"),),
            regions=("us-east-1", "eu-west-1"),
            capabilities=(
                CapabilityRequest(id="s3.inventory", version="1.0.0"),
            ),
        )

        # Profile says s3 is global
        profile_items = (
            RequiredProfileItem(
                capability_id="s3.inventory",
                capability_version="1.0.0",
                target_scope="global",
            ),
        )

        manifest = registry.snapshot()
        plan = _plan(
            request, manifest, registry, processor,
            profile_items=profile_items,
        )

        s3_units = [u for u in plan.units if u.capability_id == "s3.inventory"]
        # Should be 1 unit (global, once per account) not 2 (regional)
        assert len(s3_units) == 1
        assert s3_units[0].region_scope == "aws-global"
