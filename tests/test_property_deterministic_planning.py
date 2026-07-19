# Feature: agentic-aws-assessment, Property 3: Plan generation is deterministic and capability-isolated
# Validates: Requirements 2.3, 2.4, 6.1
"""
Property-based test for deterministic, capability-isolated plan generation.

This test validates that for ALL valid canonical-equivalent requests and
unchanged registry/profile snapshots:
1. Determinism (Req 2.3): Same canonical InvocationRequest + same registry
   snapshot always produces the same ExecutionPlan (same units, same order,
   same plan_digest, same unit_ids).
2. Capability Isolation (Req 2.4): A request for capability X (with
   prerequisites) only includes X and its declared transitive prerequisites —
   no unrelated capabilities appear in the plan.
3. Target Expansion (Req 6.1): Multi-account/multi-region targets produce
   one unit per capability-target pair, all accounted for.
"""

from __future__ import annotations

from typing import Any, Mapping

import hypothesis.strategies as st
from hypothesis import HealthCheck, given, settings

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
# FakeCollector for testing
# ---------------------------------------------------------------------------


class FakeCollector:
    """A minimal Collector implementation for property testing."""

    def collect(
        self,
        capability_id: str,
        capability_version: str,
        account_id: str,
        region_scope: str,
        parameters: Mapping[str, Any],
        session: Any,
    ) -> CollectorOutcome:
        return CollectorOutcome(status="succeeded")


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Capability ID building blocks
_CAP_PREFIXES = ["ec2", "s3", "iam", "rds", "vpc"]
_CAP_SUFFIXES = ["inventory", "audit", "scan", "check", "list"]

_capability_id_strategy = st.builds(
    lambda p, s: f"{p}.{s}",
    st.sampled_from(_CAP_PREFIXES),
    st.sampled_from(_CAP_SUFFIXES),
)

# Account IDs (12-digit AWS format)
_ACCOUNT_IDS = st.sampled_from([
    "111111111111", "222222222222", "333333333333",
])

# AWS region names
_REGIONS = st.sampled_from([
    "us-east-1", "eu-west-1", "ap-southeast-1",
])


@st.composite
def deterministic_planning_inputs(draw: st.DrawFn):
    """
    Generate a registry with a valid prerequisite DAG, a valid request
    selecting some capabilities, and multiple target pairs.

    Returns (capability_entries, registration_order, request, expected_cap_ids)
    where:
    - capability_entries: list of dicts describing each capability
    - registration_order: permuted indices for registration order
    - request: valid InvocationRequest
    - expected_cap_ids: set of capability IDs expected in the plan
      (requested + transitive prerequisites)
    """
    # 1. Generate 2-5 unique capability IDs
    num_capabilities = draw(st.integers(min_value=2, max_value=5))
    cap_ids = draw(
        st.lists(
            _capability_id_strategy,
            min_size=num_capabilities,
            max_size=num_capabilities,
            unique=True,
        )
    )

    # 2. Build a valid DAG: each capability can only depend on earlier ones
    #    (topological order guaranteed by construction)
    capabilities: list[dict[str, Any]] = []
    for i, cap_id in enumerate(cap_ids):
        # Prerequisites can only reference capabilities with lower index
        possible_prereqs = cap_ids[:i]
        if possible_prereqs:
            # Draw 0 to min(2, len(possible_prereqs)) prerequisites
            max_prereqs = min(2, len(possible_prereqs))
            num_prereqs = draw(st.integers(min_value=0, max_value=max_prereqs))
            prereqs = draw(
                st.lists(
                    st.sampled_from(possible_prereqs),
                    min_size=num_prereqs,
                    max_size=num_prereqs,
                    unique=True,
                )
            )
        else:
            prereqs = []

        capabilities.append({
            "capability_id": cap_id,
            "version": SemVer(1, 0, 0),
            "prerequisites": tuple(prereqs),
        })

    # 3. Generate a shuffled registration order
    indices = list(range(len(capabilities)))
    # We must register in topological order (prerequisites first), so we
    # generate a valid topological ordering that respects dependencies
    registration_order = _generate_valid_registration_order(capabilities, draw)

    # 4. Select 1-3 capabilities to request (from those available)
    num_requested = draw(st.integers(min_value=1, max_value=min(3, len(cap_ids))))
    requested_cap_ids = draw(
        st.lists(
            st.sampled_from(cap_ids),
            min_size=num_requested,
            max_size=num_requested,
            unique=True,
        )
    )

    # 5. Compute expected capabilities (requested + transitive prerequisites)
    expected_cap_ids = _compute_transitive_closure(requested_cap_ids, capabilities)

    # 6. Generate 1-3 accounts and 1-3 regions
    num_accounts = draw(st.integers(min_value=1, max_value=3))
    accounts = draw(
        st.lists(
            _ACCOUNT_IDS,
            min_size=num_accounts,
            max_size=num_accounts,
            unique=True,
        )
    )

    num_regions = draw(st.integers(min_value=1, max_value=3))
    regions = draw(
        st.lists(
            _REGIONS,
            min_size=num_regions,
            max_size=num_regions,
            unique=True,
        )
    )

    # 7. Build the InvocationRequest
    request = InvocationRequest(
        schema_id="invocation-request",
        schema_version="1.0.0",
        capabilities=tuple(
            CapabilityRequest(id=cap_id, version="1.0.0", parameters={})
            for cap_id in requested_cap_ids
        ),
        profile=None,
        targets=tuple(
            AccountTarget(account_id=acc) for acc in accounts
        ),
        regions=tuple(regions),
        execution_context=ExecutionContext(
            caller_id="agent/test",
            correlation_id="corr-property-test",
            idempotency_key=None,
            purpose="property-test",
            timeout_seconds=3600,
        ),
    )

    return (capabilities, registration_order, request, expected_cap_ids, accounts, regions)


def _generate_valid_registration_order(
    capabilities: list[dict[str, Any]], draw: st.DrawFn
) -> list[int]:
    """
    Generate a valid topological registration order: prerequisites are
    always registered before dependents. Among valid orderings, we
    shuffle to test different insertion sequences.
    """
    # Build dependency info
    cap_id_to_idx = {c["capability_id"]: i for i, c in enumerate(capabilities)}
    in_degree = [0] * len(capabilities)
    for i, cap in enumerate(capabilities):
        for prereq_id in cap["prerequisites"]:
            if prereq_id in cap_id_to_idx:
                in_degree[i] += 1

    # Kahn's algorithm with randomized selection among ready nodes
    ready = [i for i in range(len(capabilities)) if in_degree[i] == 0]
    order: list[int] = []

    while ready:
        # Pick a random ready node
        pick_idx = draw(st.integers(min_value=0, max_value=len(ready) - 1))
        chosen = ready.pop(pick_idx)
        order.append(chosen)

        # Update in-degrees
        chosen_id = capabilities[chosen]["capability_id"]
        for i, cap in enumerate(capabilities):
            if chosen_id in cap["prerequisites"]:
                in_degree[i] -= 1
                if in_degree[i] == 0:
                    ready.append(i)

    return order


def _compute_transitive_closure(
    requested_ids: list[str], capabilities: list[dict[str, Any]]
) -> set[str]:
    """Compute the transitive prerequisite closure for requested capabilities."""
    cap_map = {c["capability_id"]: c for c in capabilities}
    closure: set[str] = set()
    stack = list(requested_ids)

    while stack:
        current = stack.pop()
        if current in closure:
            continue
        closure.add(current)
        cap = cap_map.get(current)
        if cap:
            for prereq_id in cap["prerequisites"]:
                if prereq_id not in closure:
                    stack.append(prereq_id)

    return closure


# ---------------------------------------------------------------------------
# Helper: build registry from capabilities in specified order
# ---------------------------------------------------------------------------


def _build_registry(
    capabilities: list[dict[str, Any]],
    registration_order: list[int],
) -> CapabilityRegistryImpl:
    """Build a registry by registering capabilities in the given order."""
    registry = CapabilityRegistryImpl()
    collector = FakeCollector()

    for idx in registration_order:
        cap = capabilities[idx]
        descriptor = CapabilityDescriptor(
            capability_id=cap["capability_id"],
            version=cap["version"],
            input_schema_ref=f"{cap['capability_id']}-input/1.0.0",
            output_schema_ref=f"{cap['capability_id']}-output/1.0.0",
            error_schema_ref="structured-error/1.0.0",
            permissions=(f"{cap['capability_id']}:Read",),
            allowed_operations=(f"{cap['capability_id']}:Describe",),
            prerequisites=cap["prerequisites"],
            support_status="active",
        )
        registry.register(descriptor, collector)

    return registry


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(data=deterministic_planning_inputs())
def test_plan_generation_is_deterministic_and_capability_isolated(
    data: tuple,
) -> None:
    """
    Property 3: Plan generation is deterministic and capability-isolated.

    **Validates: Requirements 2.3, 2.4, 6.1**

    Given a set of capabilities with a valid prerequisite DAG, a valid request,
    and multi-account/multi-region targets:
    1. Same request + same registry produces identical plans regardless of
       registration order (determinism, Req 2.3)
    2. Plan contains only requested capabilities and their transitive
       prerequisites — no unrelated capabilities (isolation, Req 2.4)
    3. Plan produces one unit per resolved-capability × target-pair
       (expansion, Req 6.1)
    4. Units are topologically ordered: prerequisite units precede dependent
       units for same target pair
    """
    (capabilities, registration_order, request, expected_cap_ids,
     accounts, regions) = data

    processor = CanonicalSchemaProcessor()

    # --- Build registry in the generated order ---
    registry1 = _build_registry(capabilities, registration_order)
    manifest1 = registry1.snapshot()

    # --- Build registry in reversed valid topological order ---
    # Use a different valid order: reverse the generated order
    # But we need a valid topological order, so let's just reverse
    # the original order — since it's already valid topologically,
    # we build a second registry with natural index order (also valid
    # since capabilities are constructed with prerequisites only from
    # earlier indices)
    natural_order = list(range(len(capabilities)))
    registry2 = _build_registry(capabilities, natural_order)
    manifest2 = registry2.snapshot()

    # --- Generate plans from both registries ---
    plan1 = _plan(request, manifest1, registry1, processor)
    plan2 = _plan(request, manifest2, registry2, processor)

    # === PROPERTY 1: DETERMINISM (Req 2.3) ===
    # Same request + same registry content -> same plan regardless of
    # registration order
    assert plan1.plan_digest == plan2.plan_digest, (
        f"Plans should be identical regardless of registration order. "
        f"plan1.plan_digest={plan1.plan_digest}, "
        f"plan2.plan_digest={plan2.plan_digest}"
    )
    assert len(plan1.units) == len(plan2.units), (
        "Plans should have same number of units"
    )
    for i, (u1, u2) in enumerate(zip(plan1.units, plan2.units)):
        assert u1.unit_id == u2.unit_id, (
            f"Unit {i}: unit_ids differ: {u1.unit_id} vs {u2.unit_id}"
        )
        assert u1.capability_id == u2.capability_id, (
            f"Unit {i}: capability_ids differ"
        )
        assert u1.account_id == u2.account_id, (
            f"Unit {i}: account_ids differ"
        )
        assert u1.region_scope == u2.region_scope, (
            f"Unit {i}: region_scopes differ"
        )
        assert u1.ordinal == u2.ordinal, (
            f"Unit {i}: ordinals differ"
        )

    # Also verify calling _plan twice with same registry yields same result
    plan1_repeat = _plan(request, manifest1, registry1, processor)
    assert plan1.plan_digest == plan1_repeat.plan_digest, (
        "Repeated planning with same inputs must be deterministic"
    )

    # === PROPERTY 2: CAPABILITY ISOLATION (Req 2.4) ===
    # Only requested capabilities and their transitive prerequisites
    plan_cap_ids = {unit.capability_id for unit in plan1.units}
    assert plan_cap_ids == expected_cap_ids, (
        f"Plan capabilities should be exactly the requested + transitive "
        f"prerequisites. Got {plan_cap_ids}, expected {expected_cap_ids}"
    )

    # No unrelated capabilities
    all_cap_ids = {c["capability_id"] for c in capabilities}
    unrelated = plan_cap_ids - expected_cap_ids
    assert len(unrelated) == 0, (
        f"Unrelated capabilities found in plan: {unrelated}"
    )

    # === PROPERTY 3: TARGET EXPANSION (Req 6.1) ===
    # One unit per resolved-capability × (account, region) pair
    # Normalize targets the same way the planner does
    normalized_targets = sorted(
        {(acc, reg) for acc in accounts for reg in regions}
    )
    expected_unit_count = len(expected_cap_ids) * len(normalized_targets)
    assert len(plan1.units) == expected_unit_count, (
        f"Expected {expected_unit_count} units "
        f"({len(expected_cap_ids)} capabilities × {len(normalized_targets)} targets), "
        f"got {len(plan1.units)}"
    )

    # Verify each capability-target pair appears exactly once
    seen_pairs: set[tuple[str, str, str]] = set()
    for unit in plan1.units:
        pair = (unit.capability_id, unit.account_id, unit.region_scope)
        assert pair not in seen_pairs, (
            f"Duplicate unit for capability-target pair: {pair}"
        )
        seen_pairs.add(pair)

    # === PROPERTY 4: TOPOLOGICAL ORDERING ===
    # Prerequisite units precede dependent units for same target pair
    cap_prereqs = {c["capability_id"]: set(c["prerequisites"]) for c in capabilities}
    unit_positions: dict[tuple[str, str, str], int] = {}
    for i, unit in enumerate(plan1.units):
        unit_positions[(unit.capability_id, unit.account_id, unit.region_scope)] = i

    for unit in plan1.units:
        cap_id = unit.capability_id
        if cap_id in cap_prereqs:
            for prereq_id in cap_prereqs[cap_id]:
                if prereq_id in expected_cap_ids:
                    prereq_key = (prereq_id, unit.account_id, unit.region_scope)
                    unit_key = (cap_id, unit.account_id, unit.region_scope)
                    assert unit_positions[prereq_key] < unit_positions[unit_key], (
                        f"Prerequisite '{prereq_id}' should precede "
                        f"'{cap_id}' for target ({unit.account_id}, {unit.region_scope})"
                    )
