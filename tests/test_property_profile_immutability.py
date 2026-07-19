# Feature: agentic-aws-assessment, Property 6: Published profiles are immutable and version-consistent
# Validates: Requirements 5.1, 5.2, 5.3, 5.4
"""
Property-based test for Assessment Profile immutability and version consistency.

This test validates that regardless of profile mutations and release scenarios:
1. Immutability: Once a profile is published, resolving it always returns identical content
2. Idempotent publication: Publishing the same profile twice returns the same digest
3. Content address: Two different profiles with the same version are rejected
4. Major-version isolation: Incompatible changes (required capabilities, fields,
   region rule, completeness threshold) require a new major version
5. Version consistency: The digest computed for a profile is deterministic and
   independent of registration order or other operations
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import hypothesis.strategies as st
from hypothesis import HealthCheck, given, settings

from agentic.models import (
    AssessmentProfile,
    CollectionWindow,
    RegionRule,
    RequiredProfileItem,
    SemVer,
)
from agentic.profile_registry import (
    AssessmentProfileRegistryImpl,
    ProfilePublicationError,
)


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_profile_id_strategy = st.text(
    min_size=1,
    max_size=30,
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"),
        whitelist_characters="-.",
    ),
)

_version_strategy = st.builds(
    SemVer,
    st.integers(1, 5),
    st.integers(0, 10),
    st.integers(0, 10),
)

_capability_id_strategy = st.text(
    min_size=1,
    max_size=20,
    alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-."),
)

_required_item_strategy = st.builds(
    RequiredProfileItem,
    capability_id=_capability_id_strategy,
    capability_version=st.from_regex(r"[1-9]\.[0-9]\.[0-9]", fullmatch=True),
    required_fields=st.tuples(
        st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("Ll",)))
    ).map(lambda t: t),
    target_scope=st.sampled_from(["global", "regional", "derived"]),
    required_permissions=st.tuples(
        st.text(min_size=1, max_size=15, alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters=":"))
    ).map(lambda t: t),
    not_applicable_rule=st.none(),
)

_region_rule_strategy = st.builds(
    RegionRule,
    mode=st.sampled_from(["explicit", "discovery", "global-only"]),
    explicit_regions=st.tuples(
        st.sampled_from(["us-east-1", "eu-west-1", "ap-southeast-1"])
    ).map(lambda t: t),
)

_collection_window_strategy = st.builds(
    CollectionWindow,
    period_type=st.sampled_from(["monthly", "weekly", "daily"]),
    start=st.just("2025-01-01T00:00:00Z"),
    end=st.just("2025-01-31T23:59:59Z"),
)

_completeness_threshold_strategy = st.decimals(
    min_value=Decimal("0.01"),
    max_value=Decimal("1.00"),
    places=2,
)


@st.composite
def valid_profile_data(draw: st.DrawFn):
    """Generate a valid AssessmentProfile with random but valid data."""
    profile_id = draw(_profile_id_strategy)
    version = draw(_version_strategy)
    items = draw(
        st.lists(_required_item_strategy, min_size=1, max_size=5).map(tuple)
    )
    region_rule = draw(_region_rule_strategy)
    collection_window = draw(_collection_window_strategy)
    completeness_threshold = draw(_completeness_threshold_strategy)

    profile = AssessmentProfile(
        schema_id="assessment-profile",
        schema_version="1.0.0",
        profile_id=profile_id,
        version=version,
        effective_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        status="active",
        items=items,
        region_rule=region_rule,
        collection_window=collection_window,
        completeness_threshold=completeness_threshold,
        manifest_digest="",
    )
    return profile


@st.composite
def mutation_scenario(draw: st.DrawFn):
    """
    Generate a profile and a mutation that constitutes an incompatible change.

    Returns (original_profile, mutated_profile_same_major, mutated_profile_new_major)
    """
    profile = draw(valid_profile_data())

    # Choose a mutation type
    mutation_type = draw(st.sampled_from([
        "change_items",
        "change_threshold",
        "change_region_rule",
    ]))

    if mutation_type == "change_items":
        # Generate a new item list that differs from the original
        new_item = draw(_required_item_strategy)
        new_items = (new_item,)
        # Ensure it's actually different
        if new_items == profile.items:
            new_items = (
                RequiredProfileItem(
                    capability_id="mutated.capability",
                    capability_version="9.9.9",
                    required_fields=("mutated_field",),
                    target_scope="regional",
                    required_permissions=("mutated:Permission",),
                    not_applicable_rule=None,
                ),
            )
        mutated_same_major = AssessmentProfile(
            schema_id=profile.schema_id,
            schema_version=profile.schema_version,
            profile_id=profile.profile_id,
            version=SemVer(profile.version.major, profile.version.minor + 1, 0),
            effective_at=profile.effective_at,
            status=profile.status,
            items=new_items,
            region_rule=profile.region_rule,
            collection_window=profile.collection_window,
            completeness_threshold=profile.completeness_threshold,
            manifest_digest=profile.manifest_digest,
        )
        mutated_new_major = AssessmentProfile(
            schema_id=profile.schema_id,
            schema_version=profile.schema_version,
            profile_id=profile.profile_id,
            version=SemVer(profile.version.major + 1, 0, 0),
            effective_at=profile.effective_at,
            status=profile.status,
            items=new_items,
            region_rule=profile.region_rule,
            collection_window=profile.collection_window,
            completeness_threshold=profile.completeness_threshold,
            manifest_digest=profile.manifest_digest,
        )

    elif mutation_type == "change_threshold":
        # Change completeness threshold
        new_threshold = Decimal("0.50") if profile.completeness_threshold != Decimal("0.50") else Decimal("0.75")
        mutated_same_major = AssessmentProfile(
            schema_id=profile.schema_id,
            schema_version=profile.schema_version,
            profile_id=profile.profile_id,
            version=SemVer(profile.version.major, profile.version.minor + 1, 0),
            effective_at=profile.effective_at,
            status=profile.status,
            items=profile.items,
            region_rule=profile.region_rule,
            collection_window=profile.collection_window,
            completeness_threshold=new_threshold,
            manifest_digest=profile.manifest_digest,
        )
        mutated_new_major = AssessmentProfile(
            schema_id=profile.schema_id,
            schema_version=profile.schema_version,
            profile_id=profile.profile_id,
            version=SemVer(profile.version.major + 1, 0, 0),
            effective_at=profile.effective_at,
            status=profile.status,
            items=profile.items,
            region_rule=profile.region_rule,
            collection_window=profile.collection_window,
            completeness_threshold=new_threshold,
            manifest_digest=profile.manifest_digest,
        )

    else:  # change_region_rule
        # Change region rule mode
        new_mode = "discovery" if profile.region_rule.mode != "discovery" else "explicit"
        new_region_rule = RegionRule(mode=new_mode, explicit_regions=("us-west-2",))
        mutated_same_major = AssessmentProfile(
            schema_id=profile.schema_id,
            schema_version=profile.schema_version,
            profile_id=profile.profile_id,
            version=SemVer(profile.version.major, profile.version.minor + 1, 0),
            effective_at=profile.effective_at,
            status=profile.status,
            items=profile.items,
            region_rule=new_region_rule,
            collection_window=profile.collection_window,
            completeness_threshold=profile.completeness_threshold,
            manifest_digest=profile.manifest_digest,
        )
        mutated_new_major = AssessmentProfile(
            schema_id=profile.schema_id,
            schema_version=profile.schema_version,
            profile_id=profile.profile_id,
            version=SemVer(profile.version.major + 1, 0, 0),
            effective_at=profile.effective_at,
            status=profile.status,
            items=profile.items,
            region_rule=new_region_rule,
            collection_window=profile.collection_window,
            completeness_threshold=profile.completeness_threshold,
            manifest_digest=profile.manifest_digest,
        )

    return profile, mutated_same_major, mutated_new_major


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(data=mutation_scenario())
def test_published_profiles_are_immutable_and_version_consistent(
    data: tuple[AssessmentProfile, AssessmentProfile, AssessmentProfile],
) -> None:
    """
    Property 6: Published profiles are immutable and version-consistent.

    **Validates: Requirements 5.1, 5.2, 5.3, 5.4**

    Given a valid profile and incompatible mutations, this test verifies:
    - Publish returns a digest; resolving the profile returns identical content
    - Publishing the same profile again (idempotent) returns the same digest
    - Publishing different content at the same version raises ProfilePublicationError
    - Incompatible changes within the same major version raise ProfilePublicationError
    - Incompatible changes at a new major version succeed
    - Digest computation is deterministic regardless of other operations
    """
    original, mutated_same_major, mutated_new_major = data

    registry = AssessmentProfileRegistryImpl()

    # --- IMMUTABILITY: Publish and resolve returns identical content ---
    digest1 = registry.publish(original)
    assert isinstance(digest1, str) and len(digest1) > 0, (
        "Publish must return a non-empty digest"
    )

    resolved = registry.resolve(original.profile_id, str(original.version))
    assert resolved == original, (
        "Resolving a published profile must return identical content"
    )

    # --- IDEMPOTENT PUBLICATION: Same content, same digest ---
    digest2 = registry.publish(original)
    assert digest1 == digest2, (
        "Publishing the same profile content again must return the same digest "
        "(idempotent publication)"
    )

    # --- CONTENT ADDRESS: Different content at same version is rejected ---
    # Create a profile with same profile_id and version but different content
    different_content = AssessmentProfile(
        schema_id=original.schema_id,
        schema_version=original.schema_version,
        profile_id=original.profile_id,
        version=original.version,
        effective_at=original.effective_at,
        status=original.status,
        items=(
            RequiredProfileItem(
                capability_id="conflict.capability",
                capability_version="1.0.0",
                required_fields=("conflicting_field",),
                target_scope="regional",
                required_permissions=("conflict:Read",),
                not_applicable_rule=None,
            ),
        ),
        region_rule=RegionRule(mode="global-only", explicit_regions=()),
        collection_window=CollectionWindow(
            period_type="daily", start="2025-06-01T00:00:00Z", end="2025-06-01T23:59:59Z"
        ),
        completeness_threshold=Decimal("0.99"),
        manifest_digest="",
    )
    try:
        registry.publish(different_content)
        assert False, (
            "Publishing different content at the same version must raise "
            "ProfilePublicationError"
        )
    except ProfilePublicationError as e:
        assert e.profile_id == original.profile_id
        assert e.version == str(original.version)

    # --- MAJOR-VERSION ISOLATION: Incompatible change within same major raises ---
    try:
        registry.publish(mutated_same_major)
        assert False, (
            "Incompatible changes within the same major version must raise "
            "ProfilePublicationError"
        )
    except ProfilePublicationError as e:
        assert e.profile_id == original.profile_id
        assert "Incompatible" in str(e) or "incompatible" in str(e).lower(), (
            "Error message must mention incompatible changes"
        )

    # --- MAJOR-VERSION ISOLATION: Incompatible change at new major succeeds ---
    digest_new_major = registry.publish(mutated_new_major)
    assert isinstance(digest_new_major, str) and len(digest_new_major) > 0, (
        "Incompatible changes at a new major version must succeed"
    )

    # --- VERSION CONSISTENCY: Digest is deterministic ---
    # Create a fresh registry and publish the same profile to verify
    # the digest is independent of other operations
    registry2 = AssessmentProfileRegistryImpl()
    digest_fresh = registry2.publish(original)
    assert digest1 == digest_fresh, (
        "Digest must be deterministic and independent of other operations "
        "or registration order"
    )

    # Also verify the new major version has consistent digest across registries
    registry3 = AssessmentProfileRegistryImpl()
    # First publish original so that new major is valid in context
    registry3.publish(original)
    digest_new_major_fresh = registry3.publish(mutated_new_major)
    assert digest_new_major == digest_new_major_fresh, (
        "Digest for new major version must be consistent across registries"
    )
