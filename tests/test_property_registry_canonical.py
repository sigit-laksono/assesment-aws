# Feature: agentic-aws-assessment, Property 1: Registry snapshot is complete, valid, and canonical
# Validates: Requirements 1.1, 1.2, 1.3, 1.4, 11.1
"""
Property-based test for Capability Registry canonical snapshot.

This test validates that regardless of insertion order, the registry snapshot:
1. Complete: contains ALL registered capabilities (no silent omission)
2. Valid: every capability has non-empty capability_id, version, schema refs,
   permissions, and allowed_operations (Req 1.1, 11.1)
3. Canonical: ordering is always (capability_id, major, minor, patch) (Req 1.3)
4. Digest stable: same content -> same digest regardless of insertion order
5. Duplicate rejection: duplicate (capability_id, major_version) raises
   DuplicateCapabilityError (Req 1.2)
6. Lifecycle metadata: deprecated/removed capabilities have lifecycle with
   replacement and end date (Req 1.4)
"""

from __future__ import annotations

from typing import Any, Mapping

import hypothesis.strategies as st
from hypothesis import HealthCheck, given, settings

from agentic.models import (
    CapabilityDescriptor,
    CapabilityManifest,
    CollectorOutcome,
    LifecycleMetadata,
    SemVer,
)
from agentic.registry import (
    CapabilityRegistryImpl,
    DuplicateCapabilityError,
    RegistrationError,
)


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

# Pre-defined capability ID prefixes and suffixes for fast generation
_CAP_PREFIXES = [
    "ec2", "s3", "iam", "rds", "vpc", "eks", "ecs", "alb",
    "nlb", "kms", "waf", "sns", "sqs", "glue", "msk", "ecr",
    "efs", "ebs", "nat", "rt53", "cf", "ddb", "elc", "bkp",
]
_CAP_SUFFIXES = [
    "inventory", "audit", "scan", "check", "list", "describe",
    "status", "config", "policy", "metrics", "usage", "tags",
]

_capability_id_strategy = st.builds(
    lambda p, s: f"{p}.{s}",
    st.sampled_from(_CAP_PREFIXES),
    st.sampled_from(_CAP_SUFFIXES),
)


@st.composite
def unique_capability_entries(draw: st.DrawFn):
    """
    Generate a list of unique (capability_id, major_version) pairs with
    random minor/patch, plus a shuffled insertion order.

    Returns (entries, shuffled_indices) where entries is the canonical list
    and shuffled_indices is a permutation for insertion order.
    """
    # Generate between 2 and 12 unique (capability_id, major) combinations
    num_entries = draw(st.integers(min_value=2, max_value=12))

    # Draw unique (capability_id, major) pairs using st.lists with unique_by
    pairs = draw(
        st.lists(
            st.tuples(
                _capability_id_strategy,
                st.integers(min_value=1, max_value=5),
            ),
            min_size=num_entries,
            max_size=num_entries,
            unique=True,
        )
    )

    entries: list[dict[str, Any]] = []
    for cap_id, major in pairs:
        minor = draw(st.integers(min_value=0, max_value=99))
        patch = draw(st.integers(min_value=0, max_value=99))

        # Randomly assign support status (weighted toward active)
        status = draw(
            st.sampled_from(["active", "active", "active", "deprecated", "removed"])
        )

        lifecycle = None
        if status in ("deprecated", "removed"):
            lifecycle = LifecycleMetadata(
                replacement_capability_id=f"{cap_id}.v{major + 1}",
                support_end_date="2026-12-31",
                deprecation_reason=f"Replaced by v{major + 1}",
            )

        entries.append({
            "capability_id": cap_id,
            "major": major,
            "minor": minor,
            "patch": patch,
            "support_status": status,
            "lifecycle": lifecycle,
        })

    # Generate a shuffled insertion order
    indices = list(range(len(entries)))
    shuffled = draw(st.permutations(indices))

    return entries, list(shuffled)


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(data=unique_capability_entries())
def test_registry_snapshot_is_complete_valid_and_canonical(
    data: tuple[list[dict[str, Any]], list[int]],
) -> None:
    """
    Property 1: Registry snapshot is complete, valid, and canonical.

    Validates: Requirements 1.1, 1.2, 1.3, 1.4, 11.1

    Given a set of unique (capability_id, major_version) capabilities registered
    in arbitrary order, the snapshot must be:
    - Complete (all registered capabilities present)
    - Valid (non-empty required fields)
    - Canonically ordered by (capability_id, major, minor, patch)
    - Digest-stable (same content regardless of insertion order)
    - Duplicate-rejecting for same (capability_id, major_version)
    - Lifecycle-valid for deprecated/removed capabilities
    """
    entries, shuffled_indices = data
    if not entries:
        return

    collector = FakeCollector()

    # --- Register in shuffled order ---
    registry = CapabilityRegistryImpl()
    for idx in shuffled_indices:
        entry = entries[idx]
        descriptor = CapabilityDescriptor(
            capability_id=entry["capability_id"],
            version=SemVer(entry["major"], entry["minor"], entry["patch"]),
            input_schema_ref=f"{entry['capability_id']}-input/1.0.0",
            output_schema_ref=f"{entry['capability_id']}-output/1.0.0",
            error_schema_ref="structured-error/1.0.0",
            permissions=(f"{entry['capability_id']}:Read",),
            allowed_operations=(f"{entry['capability_id']}:Describe",),
            support_status=entry["support_status"],
            lifecycle=entry["lifecycle"],
        )
        registry.register(descriptor, collector)

    manifest = registry.snapshot()

    # --- Property: COMPLETE ---
    # The manifest contains ALL registered capabilities
    assert len(manifest.capabilities) == len(entries)

    registered_keys = {
        (e["capability_id"], e["major"], e["minor"], e["patch"])
        for e in entries
    }
    manifest_keys = {
        (c.capability_id, c.version.major, c.version.minor, c.version.patch)
        for c in manifest.capabilities
    }
    assert registered_keys == manifest_keys, "Manifest is missing capabilities"

    # --- Property: VALID ---
    # Every capability has non-empty required fields (Req 1.1, 11.1)
    for cap in manifest.capabilities:
        assert cap.capability_id != "", "capability_id must be non-empty"
        assert cap.version != SemVer(0, 0, 0), "version must not be zero"
        assert cap.input_schema_ref != "", "input_schema_ref must be non-empty"
        assert cap.output_schema_ref != "", "output_schema_ref must be non-empty"
        assert cap.error_schema_ref != "", "error_schema_ref must be non-empty"
        assert len(cap.permissions) > 0, "permissions must be non-empty"
        assert len(cap.allowed_operations) > 0, "allowed_operations must be non-empty"

    # --- Property: CANONICAL ordering ---
    # Sorted by (capability_id, major, minor, patch) regardless of insertion order
    sort_keys = [
        (c.capability_id, c.version.major, c.version.minor, c.version.patch)
        for c in manifest.capabilities
    ]
    assert sort_keys == sorted(sort_keys), (
        "Manifest must be canonically ordered by (capability_id, major, minor, patch)"
    )

    # --- Property: DIGEST STABLE ---
    # Register same content in natural order and verify digest matches
    registry2 = CapabilityRegistryImpl()
    for entry in entries:  # register in natural (non-shuffled) order
        descriptor = CapabilityDescriptor(
            capability_id=entry["capability_id"],
            version=SemVer(entry["major"], entry["minor"], entry["patch"]),
            input_schema_ref=f"{entry['capability_id']}-input/1.0.0",
            output_schema_ref=f"{entry['capability_id']}-output/1.0.0",
            error_schema_ref="structured-error/1.0.0",
            permissions=(f"{entry['capability_id']}:Read",),
            allowed_operations=(f"{entry['capability_id']}:Describe",),
            support_status=entry["support_status"],
            lifecycle=entry["lifecycle"],
        )
        registry2.register(descriptor, collector)

    manifest2 = registry2.snapshot()
    assert manifest.manifest_digest == manifest2.manifest_digest, (
        "Same content must produce same digest regardless of insertion order"
    )

    # --- Property: DUPLICATE REJECTION ---
    # Attempting to register duplicate (capability_id, major_version) raises error
    if entries:
        # Pick a random entry and try to re-register with same cap_id + major
        dup_entry = entries[0]
        dup_descriptor = CapabilityDescriptor(
            capability_id=dup_entry["capability_id"],
            version=SemVer(dup_entry["major"], 99, 99),  # different minor/patch
            input_schema_ref=f"{dup_entry['capability_id']}-input/1.0.0",
            output_schema_ref=f"{dup_entry['capability_id']}-output/1.0.0",
            error_schema_ref="structured-error/1.0.0",
            permissions=(f"{dup_entry['capability_id']}:Read",),
            allowed_operations=(f"{dup_entry['capability_id']}:Describe",),
            support_status="active",
        )
        try:
            registry.register(dup_descriptor, collector)
            assert False, "DuplicateCapabilityError should have been raised"
        except DuplicateCapabilityError as e:
            assert e.capability_id == dup_entry["capability_id"]
            assert e.major_version == dup_entry["major"]

    # --- Property: LIFECYCLE METADATA ---
    # Deprecated/removed capabilities have lifecycle with replacement and end date
    for cap in manifest.capabilities:
        if cap.support_status in ("deprecated", "removed"):
            assert cap.lifecycle is not None, (
                f"Capability '{cap.capability_id}' is {cap.support_status} "
                f"but has no lifecycle metadata"
            )
            assert cap.lifecycle.replacement_capability_id, (
                f"Capability '{cap.capability_id}' missing replacement_capability_id"
            )
            assert cap.lifecycle.support_end_date, (
                f"Capability '{cap.capability_id}' missing support_end_date"
            )
