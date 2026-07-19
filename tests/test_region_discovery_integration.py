"""
Multi-target planning and region discovery integration tests (Task 5.5).

Covers:
- Shuffled/duplicate region discovery responses produce a sorted,
  deduplicated `region_discovery_snapshot` on the ExecutionPlan (Req 6.1, 6.2).
- The discovery snapshot is present on the plan BEFORE any regional
  collection execution unit is executed by the BoundedExecutor — i.e. the
  snapshot is part of the plan artifact itself and is available to every
  unit at execution time, not populated lazily during/after collection
  (Req 6.2).
- Global-scope capabilities ('aws-global') are represented by exactly one
  execution unit per account even when the account has many regions in
  scope, and this holds regardless of how the region discovery response is
  ordered or how many duplicates it contains (Req 6.1, 6.5).
- Execution unit IDs are stable (byte-identical) across:
    * repeated planning of the same canonical request,
    * shuffled region discovery response ordering that represents the same
      logical region set,
    * duplicate regions in the discovery response.
  (Req 6.1, 6.2, 6.5)

Uses mocked boto3-shaped Collectors and SessionFactory — no real network or
AWS calls. Uses pytest with example/table-driven cases (not Hypothesis).
"""

from __future__ import annotations

import itertools
from typing import Any, Mapping
from unittest.mock import MagicMock

import pytest

from agentic.executor import BoundedExecutor
from agentic.models import (
    AccountTarget,
    CapabilityDescriptor,
    CapabilityRequest,
    CollectorOutcome,
    ExecutionContext,
    ExecutionPlan,
    InvocationRequest,
    SemVer,
)
from agentic.orchestrator import _plan
from agentic.registry import CapabilityRegistryImpl
from agentic.schemas.processor import CanonicalSchemaProcessor


# ---------------------------------------------------------------------------
# Fakes / Fixtures — no real boto3 or network calls
# ---------------------------------------------------------------------------


class FakeCollector:
    """Minimal Collector stub. Never performs real AWS SDK calls."""

    def __init__(self, name: str = "fake") -> None:
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


class FakeSessionFactory:
    """Fake SessionFactory — returns a MagicMock session, no AWS calls."""

    def for_account(self, target: AccountTarget) -> Any:
        return MagicMock()


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
            correlation_id="corr-region-discovery",
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
        prerequisites=(),
        scope="regional",
    )
    registry.register(ec2_desc, FakeCollector("ec2"))

    return registry


def _make_regional_only_registry() -> CapabilityRegistryImpl:
    """Registry with a single regional capability, no prerequisites."""
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
    return registry


# ---------------------------------------------------------------------------
# Test: Region discovery snapshot sorted/deduplicated from shuffled/duplicate
# discovery responses (Req 6.2)
# ---------------------------------------------------------------------------


class TestDiscoverySnapshotFromShuffledDuplicateResponses:
    """Feeds shuffled/duplicate region discovery responses into the planner."""

    # Table of raw (simulated) DescribeRegions-style responses: each is an
    # unordered, duplicate-laden list of region codes for one account.
    SHUFFLED_DUPLICATE_CASES = [
        # (raw discovery response, expected sorted/deduped tuple)
        (
            ("eu-west-1", "us-east-1", "eu-west-1", "ap-southeast-1"),
            ("ap-southeast-1", "eu-west-1", "us-east-1"),
        ),
        (
            ("us-west-2", "us-west-2", "us-west-2"),
            ("us-west-2",),
        ),
        (
            ("sa-east-1", "af-south-1", "me-south-1", "af-south-1", "sa-east-1"),
            ("af-south-1", "me-south-1", "sa-east-1"),
        ),
        (
            ("us-east-1",),
            ("us-east-1",),
        ),
    ]

    @pytest.mark.parametrize(
        "raw_response,expected_sorted", SHUFFLED_DUPLICATE_CASES
    )
    def test_snapshot_is_sorted_and_deduplicated(
        self, raw_response: tuple[str, ...], expected_sorted: tuple[str, ...]
    ) -> None:
        registry = _make_regional_only_registry()
        processor = CanonicalSchemaProcessor()

        request = _make_request(
            accounts=(AccountTarget(account_id="111111111111"),),
            regions=tuple(sorted(set(raw_response))),
            capabilities=(CapabilityRequest(id="ec2.inventory", version="1.0.0"),),
        )

        discovered = {"111111111111": raw_response}

        manifest = registry.snapshot()
        plan = _plan(
            request, manifest, registry, processor,
            discovered_regions=discovered,
        )

        assert plan.region_discovery_snapshot["111111111111"] == expected_sorted

    def test_multi_account_snapshot_sorted_and_deduplicated(self) -> None:
        """Multiple accounts, each with shuffled/duplicate discovery responses."""
        registry = _make_regional_only_registry()
        processor = CanonicalSchemaProcessor()

        request = _make_request(
            accounts=(
                AccountTarget(account_id="222222222222"),
                AccountTarget(account_id="111111111111"),
            ),
            regions=("us-east-1",),
            capabilities=(CapabilityRequest(id="ec2.inventory", version="1.0.0"),),
        )

        discovered = {
            "222222222222": ("eu-west-1", "us-east-1", "eu-west-1"),
            "111111111111": ("us-west-2", "ap-southeast-1", "us-west-2", "us-west-2"),
        }

        manifest = registry.snapshot()
        plan = _plan(
            request, manifest, registry, processor,
            discovered_regions=discovered,
        )

        # Account keys sorted lexicographically
        assert list(plan.region_discovery_snapshot.keys()) == [
            "111111111111", "222222222222",
        ]
        # Each account's region values sorted and deduplicated
        assert plan.region_discovery_snapshot["111111111111"] == (
            "ap-southeast-1", "us-west-2",
        )
        assert plan.region_discovery_snapshot["222222222222"] == (
            "eu-west-1", "us-east-1",
        )

    def test_no_duplicate_region_values_survive_in_snapshot(self) -> None:
        """A heavily duplicated discovery response collapses to unique values."""
        registry = _make_regional_only_registry()
        processor = CanonicalSchemaProcessor()

        request = _make_request(
            accounts=(AccountTarget(account_id="111111111111"),),
            regions=("us-east-1",),
            capabilities=(CapabilityRequest(id="ec2.inventory", version="1.0.0"),),
        )

        raw_response = tuple(
            itertools.chain.from_iterable(
                itertools.repeat(("us-east-1", "eu-west-1", "ap-southeast-1"), 5)
            )
        )
        discovered = {"111111111111": raw_response}

        manifest = registry.snapshot()
        plan = _plan(
            request, manifest, registry, processor,
            discovered_regions=discovered,
        )

        snapshot_regions = plan.region_discovery_snapshot["111111111111"]
        assert snapshot_regions == ("ap-southeast-1", "eu-west-1", "us-east-1")
        assert len(snapshot_regions) == len(set(snapshot_regions))


# ---------------------------------------------------------------------------
# Test: Discovery snapshot exists on the plan BEFORE any unit executes
# (ordering guarantee — Req 6.2)
# ---------------------------------------------------------------------------


class TestDiscoverySnapshotPrecedesCollection:
    """
    The region discovery snapshot must be written into the ExecutionPlan as
    part of planning — before regional collection execution units are
    considered ready/executed. This is verified by observing, from inside
    every collector invocation during execution, that the plan's discovery
    snapshot is already fully populated and unchanged from the value
    computed at plan time.
    """

    def test_snapshot_populated_before_any_unit_executes(self) -> None:
        registry = _make_regional_only_registry()
        processor = CanonicalSchemaProcessor()

        request = _make_request(
            accounts=(AccountTarget(account_id="111111111111"),),
            regions=("us-east-1", "eu-west-1", "ap-southeast-1"),
            capabilities=(CapabilityRequest(id="ec2.inventory", version="1.0.0"),),
        )

        # Shuffled + duplicate raw discovery response
        raw_response = (
            "ap-southeast-1", "us-east-1", "eu-west-1", "us-east-1",
        )
        discovered = {"111111111111": raw_response}

        manifest = registry.snapshot()
        plan = _plan(
            request, manifest, registry, processor,
            discovered_regions=discovered,
        )

        # The snapshot must already be sorted/deduplicated on the plan
        # object BEFORE execute() is ever called.
        expected_snapshot = {
            "111111111111": ("ap-southeast-1", "eu-west-1", "us-east-1"),
        }
        assert plan.region_discovery_snapshot == expected_snapshot
        assert plan.units, "Plan must contain regional collection units"

        observed_snapshots_at_unit_start: list[Mapping[str, tuple[str, ...]]] = []

        def observing_collector_fn(unit: Any, session: Any) -> CollectorOutcome:
            # Record the plan's discovery snapshot exactly as observed at
            # the moment this unit begins collection.
            observed_snapshots_at_unit_start.append(plan.region_discovery_snapshot)
            return CollectorOutcome(status="succeeded", records=(), evidence=())

        executor = BoundedExecutor()
        results = executor.execute(plan, observing_collector_fn, FakeSessionFactory())

        assert len(results) == len(plan.units)
        assert all(r.status == "succeeded" for r in results)
        # Every unit observed the exact same, already-sorted/deduplicated
        # snapshot — it was never empty, partially built, or mutated later.
        assert len(observed_snapshots_at_unit_start) == len(plan.units)
        for observed in observed_snapshots_at_unit_start:
            assert observed == expected_snapshot

    def test_snapshot_unaffected_by_collection_outcomes(self) -> None:
        """Failures during collection do not retroactively change the
        already-recorded discovery snapshot."""
        registry = _make_regional_only_registry()
        processor = CanonicalSchemaProcessor()

        request = _make_request(
            accounts=(AccountTarget(account_id="111111111111"),),
            regions=("us-east-1", "eu-west-1"),
            capabilities=(CapabilityRequest(id="ec2.inventory", version="1.0.0"),),
        )

        discovered = {"111111111111": ("eu-west-1", "us-east-1", "us-east-1")}
        manifest = registry.snapshot()
        plan = _plan(
            request, manifest, registry, processor,
            discovered_regions=discovered,
        )
        pre_execution_snapshot = plan.region_discovery_snapshot

        def failing_collector_fn(unit: Any, session: Any) -> CollectorOutcome:
            return CollectorOutcome(status="failed", records=(), evidence=())

        executor = BoundedExecutor()
        executor.execute(plan, failing_collector_fn, FakeSessionFactory())

        assert plan.region_discovery_snapshot == pre_execution_snapshot


# ---------------------------------------------------------------------------
# Test: Global scope does not repeat per region (Req 6.1, 6.5)
# ---------------------------------------------------------------------------


class TestGlobalScopeDoesNotRepeatPerRegion:
    """
    Global-scope capabilities create exactly one execution unit per account
    regardless of how many regions are in scope or how the region discovery
    response was ordered/duplicated.
    """

    @pytest.mark.parametrize(
        "raw_discovery_response",
        [
            ("us-east-1", "eu-west-1", "ap-southeast-1"),
            ("ap-southeast-1", "us-east-1", "eu-west-1"),  # shuffled
            ("us-east-1", "us-east-1", "eu-west-1", "ap-southeast-1", "eu-west-1"),  # dup
        ],
    )
    def test_single_account_single_global_unit(
        self, raw_discovery_response: tuple[str, ...]
    ) -> None:
        registry = _make_registry_global_and_regional()
        processor = CanonicalSchemaProcessor()

        request = _make_request(
            accounts=(AccountTarget(account_id="111111111111"),),
            regions=tuple(sorted(set(raw_discovery_response))),
            capabilities=(
                CapabilityRequest(id="iam.identity", version="1.0.0"),
                CapabilityRequest(id="ec2.inventory", version="1.0.0"),
            ),
        )
        discovered = {"111111111111": raw_discovery_response}

        manifest = registry.snapshot()
        plan = _plan(
            request, manifest, registry, processor,
            discovered_regions=discovered,
        )

        global_units = [u for u in plan.units if u.region_scope == "aws-global"]
        assert len(global_units) == 1
        assert global_units[0].capability_id == "iam.identity"
        assert global_units[0].account_id == "111111111111"

    def test_multi_account_one_global_unit_each(self) -> None:
        """Multiple accounts each with several discovered regions still
        yield exactly one global unit per account."""
        registry = _make_registry_global_and_regional()
        processor = CanonicalSchemaProcessor()

        request = _make_request(
            accounts=(
                AccountTarget(account_id="111111111111"),
                AccountTarget(account_id="222222222222"),
            ),
            regions=("us-east-1", "eu-west-1", "ap-southeast-1", "us-west-2"),
            capabilities=(
                CapabilityRequest(id="iam.identity", version="1.0.0"),
                CapabilityRequest(id="ec2.inventory", version="1.0.0"),
            ),
        )
        # Shuffled + duplicate discovery response, different per account
        discovered = {
            "111111111111": (
                "us-west-2", "us-east-1", "eu-west-1",
                "ap-southeast-1", "us-east-1",
            ),
            "222222222222": (
                "eu-west-1", "eu-west-1", "us-west-2", "ap-southeast-1",
            ),
        }

        manifest = registry.snapshot()
        plan = _plan(
            request, manifest, registry, processor,
            discovered_regions=discovered,
        )

        global_units = [u for u in plan.units if u.region_scope == "aws-global"]
        assert len(global_units) == 2

        by_account = {u.account_id: u for u in global_units}
        assert set(by_account.keys()) == {"111111111111", "222222222222"}
        for unit in by_account.values():
            assert unit.capability_id == "iam.identity"

        # Regional units still expand to every (account, region) pair
        regional_units = [
            u for u in plan.units if u.capability_id == "ec2.inventory"
        ]
        assert len(regional_units) == 2 * 4  # 2 accounts x 4 regions


# ---------------------------------------------------------------------------
# Test: Stable execution unit IDs across shuffled/duplicate discovery input
# (Req 6.1, 6.2, 6.5)
# ---------------------------------------------------------------------------


class TestStableUnitIdsAcrossDiscoveryVariation:
    """
    Execution unit IDs remain byte-identical when:
    - the same canonical request is planned multiple times,
    - region discovery responses arrive shuffled but represent the same
      logical region set,
    - duplicate regions appear in the discovery response.
    """

    def test_repeated_planning_same_request_same_unit_ids(self) -> None:
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
        discovered = {"111111111111": ("us-east-1", "eu-west-1")}

        manifest = registry.snapshot()
        plan1 = _plan(
            request, manifest, registry, processor, discovered_regions=discovered
        )
        plan2 = _plan(
            request, manifest, registry, processor, discovered_regions=discovered
        )
        plan3 = _plan(
            request, manifest, registry, processor, discovered_regions=discovered
        )

        assert plan1.plan_digest == plan2.plan_digest == plan3.plan_digest
        ids1 = [u.unit_id for u in plan1.units]
        ids2 = [u.unit_id for u in plan2.units]
        ids3 = [u.unit_id for u in plan3.units]
        assert ids1 == ids2 == ids3

    def test_shuffled_discovery_same_logical_set_yields_identical_unit_ids(
        self,
    ) -> None:
        """Different orderings of the same logical region set (both in the
        request's own `regions` field and in the raw discovery response)
        must not change resulting unit IDs or plan digest."""
        registry = _make_regional_only_registry()
        processor = CanonicalSchemaProcessor()
        manifest = registry.snapshot()

        base_regions = {"us-east-1", "eu-west-1", "ap-southeast-1"}
        orderings = [
            ("us-east-1", "eu-west-1", "ap-southeast-1"),
            ("ap-southeast-1", "us-east-1", "eu-west-1"),
            ("eu-west-1", "ap-southeast-1", "us-east-1"),
        ]

        plans: list[ExecutionPlan] = []
        for ordering in orderings:
            assert set(ordering) == base_regions
            request = _make_request(
                accounts=(AccountTarget(account_id="111111111111"),),
                regions=ordering,
                capabilities=(
                    CapabilityRequest(id="ec2.inventory", version="1.0.0"),
                ),
            )
            discovered = {"111111111111": ordering}
            plan = _plan(
                request, manifest, registry, processor,
                discovered_regions=discovered,
            )
            plans.append(plan)

        first_ids = sorted(u.unit_id for u in plans[0].units)
        for plan in plans[1:]:
            assert sorted(u.unit_id for u in plan.units) == first_ids
            assert plan.plan_digest == plans[0].plan_digest
            assert plan.region_discovery_snapshot == plans[0].region_discovery_snapshot

    def test_duplicate_regions_in_discovery_do_not_create_duplicate_units_or_alter_ids(
        self,
    ) -> None:
        """Duplicates in the discovery response must not create duplicate
        execution units, and must not alter the unit IDs of the other
        (non-duplicated) units in the plan."""
        registry = _make_regional_only_registry()
        processor = CanonicalSchemaProcessor()
        manifest = registry.snapshot()

        request_clean = _make_request(
            accounts=(AccountTarget(account_id="111111111111"),),
            regions=("us-east-1", "eu-west-1"),
            capabilities=(CapabilityRequest(id="ec2.inventory", version="1.0.0"),),
        )
        discovered_clean = {"111111111111": ("us-east-1", "eu-west-1")}
        plan_clean = _plan(
            request_clean, manifest, registry, processor,
            discovered_regions=discovered_clean,
        )

        request_dup = _make_request(
            accounts=(AccountTarget(account_id="111111111111"),),
            regions=("us-east-1", "eu-west-1", "us-east-1", "us-east-1"),
            capabilities=(CapabilityRequest(id="ec2.inventory", version="1.0.0"),),
        )
        discovered_dup = {
            "111111111111": (
                "us-east-1", "eu-west-1", "us-east-1", "us-east-1", "eu-west-1",
            ),
        }
        plan_dup = _plan(
            request_dup, manifest, registry, processor,
            discovered_regions=discovered_dup,
        )

        # No duplicate execution units created
        assert len(plan_dup.units) == 2
        assert len(plan_clean.units) == 2

        # Same set of unit IDs, and each individual unit ID is unaffected
        clean_ids = {u.unit_id for u in plan_clean.units}
        dup_ids = {u.unit_id for u in plan_dup.units}
        assert clean_ids == dup_ids

        # Same plan digest overall
        assert plan_clean.plan_digest == plan_dup.plan_digest

        # Discovery snapshot deduplicated identically
        assert (
            plan_clean.region_discovery_snapshot
            == plan_dup.region_discovery_snapshot
        )

    def test_global_unit_id_stable_across_shuffled_duplicate_discovery(
        self,
    ) -> None:
        """A global-scope unit's ID must be stable across shuffled/duplicate
        discovery responses, since it depends only on (request_digest,
        capability_version, account_id, 'aws-global', ordinal) — none of
        which vary with discovery ordering once regions are canonicalized."""
        registry = _make_registry_global_and_regional()
        processor = CanonicalSchemaProcessor()
        manifest = registry.snapshot()

        variants = [
            ("us-east-1", "eu-west-1"),
            ("eu-west-1", "us-east-1"),  # shuffled
            ("us-east-1", "us-east-1", "eu-west-1", "eu-west-1"),  # duplicate
        ]

        global_unit_ids: set[str] = set()
        for regions in variants:
            request = _make_request(
                accounts=(AccountTarget(account_id="111111111111"),),
                regions=tuple(sorted(set(regions))),
                capabilities=(
                    CapabilityRequest(id="iam.identity", version="1.0.0"),
                    CapabilityRequest(id="ec2.inventory", version="1.0.0"),
                ),
            )
            discovered = {"111111111111": regions}
            plan = _plan(
                request, manifest, registry, processor,
                discovered_regions=discovered,
            )
            global_units = [
                u for u in plan.units if u.region_scope == "aws-global"
            ]
            assert len(global_units) == 1
            global_unit_ids.add(global_units[0].unit_id)

        assert len(global_unit_ids) == 1, (
            f"Global unit ID must be stable across discovery variants, "
            f"got distinct IDs: {global_unit_ids}"
        )
