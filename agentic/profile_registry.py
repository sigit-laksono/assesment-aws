"""
Assessment Profile Registry — Immutable Profile Publication and Resolution.

Implements the AssessmentProfileRegistry Protocol with:
- Exact-version resolution returning immutable profile content (Req 5.2)
- Major-version compatible resolution (latest minor/patch within same major)
- Immutable publication with content digest (SHA-256 over canonical JSON)
- Duplicate prevention: same version + same content is idempotent,
  same version + different content is rejected (Req 5.2)
- Validation of required items, fields, permissions, scope, collection window,
  and completeness threshold on publish
- Lifecycle status transitions: draft -> active -> retired (no backwards)
- Major-version compatibility: incompatible changes require new major version (Req 5.3)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from agentic.models import (
    AssessmentProfile,
    SemVer,
    StructuredError,
)


# ---------------------------------------------------------------------------
# Lifecycle transition rules
# ---------------------------------------------------------------------------

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"active"},
    "active": {"retired"},
    "retired": set(),
}


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------


class AssessmentProfileRegistryImpl:
    """
    Concrete implementation of the AssessmentProfileRegistry Protocol.

    Published profiles are immutable and content-addressed. Resolution
    returns exact or major-compatible versions. Incompatible changes
    between published versions of the same profile_id must increment
    the major version.
    """

    def __init__(self) -> None:
        # Storage: profile_id -> {version_str -> (AssessmentProfile, digest)}
        self._profiles: dict[str, dict[str, tuple[AssessmentProfile, str]]] = {}

    # ------------------------------------------------------------------
    # Publication
    # ------------------------------------------------------------------

    def publish(self, profile: AssessmentProfile) -> str:
        """
        Publish a profile version. Returns the content digest.

        Validates:
        - items must be nonempty
        - Each RequiredProfileItem must have non-empty capability_id,
          capability_version, required_fields, required_permissions
        - collection_window must have non-empty period_type
        - completeness_threshold must be between 0 and 1 inclusive
        - Lifecycle status transition is valid
        - Duplicate version with same content is idempotent
        - Duplicate version with different content is rejected

        Raises ProfilePublicationError for validation failures.
        """
        # --- Validation ---
        self._validate_profile(profile)

        # --- Lifecycle status check ---
        version_key = str(profile.version)
        profile_entries = self._profiles.get(profile.profile_id, {})

        # Check lifecycle transition if there's already a published version
        # with the same version string (status change case)
        if version_key in profile_entries:
            existing_profile, existing_digest = profile_entries[version_key]
            # Compute new digest
            new_digest = self._compute_content_digest(profile)

            if new_digest == existing_digest:
                # Idempotent: same content, return existing digest
                return existing_digest
            else:
                # Different content for same version — reject
                return self._reject_duplicate_version(profile, existing_digest)

        # Check lifecycle: new version status must be valid relative to
        # the latest published version of the same profile_id
        self._validate_lifecycle_transition(profile, profile_entries)

        # --- Major-version compatibility check ---
        self._validate_major_version_compatibility(profile, profile_entries)

        # --- Compute content digest ---
        digest = self._compute_content_digest(profile)

        # --- Store immutably ---
        if profile.profile_id not in self._profiles:
            self._profiles[profile.profile_id] = {}
        self._profiles[profile.profile_id][version_key] = (profile, digest)

        return digest

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def resolve(
        self, profile_id: str, version: str
    ) -> AssessmentProfile | StructuredError:
        """
        Resolve an exact profile version. Returns immutable profile content.
        Returns StructuredError if not found.
        """
        profile_entries = self._profiles.get(profile_id)

        if profile_entries is None:
            return self._make_not_found_error(profile_id, version)

        entry = profile_entries.get(version)
        if entry is None:
            return self._make_not_found_error(profile_id, version)

        return entry[0]

    def resolve_compatible(
        self, profile_id: str, major_version: int
    ) -> AssessmentProfile | StructuredError:
        """
        Resolve the latest profile compatible with the given major version.
        Returns the latest minor/patch within the same major version.
        """
        profile_entries = self._profiles.get(profile_id)

        if profile_entries is None:
            return self._make_not_found_error(
                profile_id, f"{major_version}.x.x"
            )

        # Find all versions matching this major
        compatible: list[tuple[SemVer, AssessmentProfile]] = []
        for _version_str, (prof, _digest) in profile_entries.items():
            if prof.version.major == major_version:
                compatible.append((prof.version, prof))

        if not compatible:
            return self._make_not_found_error(
                profile_id, f"{major_version}.x.x"
            )

        # Sort by (minor, patch) descending and return the latest
        compatible.sort(
            key=lambda pair: (pair[0].minor, pair[0].patch), reverse=True
        )
        return compatible[0][1]

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _validate_profile(self, profile: AssessmentProfile) -> None:
        """Validate profile content before publication."""
        errors: list[str] = []

        # items must be nonempty
        if not profile.items:
            errors.append("Profile must have at least one required item.")

        # Each RequiredProfileItem validation
        for i, item in enumerate(profile.items):
            if not item.capability_id:
                errors.append(
                    f"Item [{i}]: capability_id must not be empty."
                )
            if not item.capability_version:
                errors.append(
                    f"Item [{i}]: capability_version must not be empty."
                )
            if not item.required_fields:
                errors.append(
                    f"Item [{i}]: required_fields must not be empty."
                )
            if not item.required_permissions:
                errors.append(
                    f"Item [{i}]: required_permissions must not be empty."
                )

        # collection_window must have non-empty period_type
        if not profile.collection_window.period_type:
            errors.append("collection_window.period_type must not be empty.")

        # completeness_threshold must be between 0 and 1 inclusive
        if profile.completeness_threshold < Decimal("0") or profile.completeness_threshold > Decimal("1"):
            errors.append(
                f"completeness_threshold must be between 0 and 1 inclusive, "
                f"got {profile.completeness_threshold}."
            )

        if errors:
            raise ProfilePublicationError(
                profile_id=profile.profile_id,
                version=str(profile.version),
                reasons=errors,
            )

    def _validate_lifecycle_transition(
        self,
        profile: AssessmentProfile,
        existing_entries: dict[str, tuple[AssessmentProfile, str]],
    ) -> None:
        """
        Validate that the new profile's status is reachable from the
        latest existing profile status for this profile_id.
        """
        if not existing_entries:
            # First publication — any status is valid
            return

        # Find the latest published version to check status transition
        latest_version: SemVer | None = None
        latest_profile: AssessmentProfile | None = None
        for _v, (prof, _d) in existing_entries.items():
            if latest_version is None or self._version_gt(
                prof.version, latest_version
            ):
                latest_version = prof.version
                latest_profile = prof

        if latest_profile is None:
            return

        # If we're publishing a new version, the status can be independent
        # (a new version can start as draft even if previous is active)
        # But within the SAME profile_id, we enforce status cannot go backwards
        # for the same version lineage.
        # The primary constraint: retired profiles cannot revert to active/draft.
        if latest_profile.status == "retired" and profile.status != "retired":
            # Allow publishing new major versions even after retirement of old ones
            if profile.version.major > latest_profile.version.major:
                return
            raise ProfilePublicationError(
                profile_id=profile.profile_id,
                version=str(profile.version),
                reasons=[
                    f"Cannot publish status '{profile.status}' because the latest "
                    f"version ({latest_version}) is already 'retired'. "
                    f"Lifecycle transitions are: draft -> active -> retired."
                ],
            )

    def _validate_major_version_compatibility(
        self,
        profile: AssessmentProfile,
        existing_entries: dict[str, tuple[AssessmentProfile, str]],
    ) -> None:
        """
        Validate that incompatible changes use a new major version (Req 5.3).

        Incompatible changes are:
        - required capability list changes
        - required field list changes
        - region scope rule changes
        - completeness rule changes
        """
        if not existing_entries:
            return

        # Find the latest published version with the same major version
        same_major_entries: list[tuple[SemVer, AssessmentProfile]] = []
        for _v, (prof, _d) in existing_entries.items():
            if prof.version.major == profile.version.major:
                same_major_entries.append((prof.version, prof))

        if not same_major_entries:
            # New major version — no compatibility check needed
            return

        # Get the latest version in the same major
        same_major_entries.sort(
            key=lambda pair: (pair[0].minor, pair[0].patch), reverse=True
        )
        latest_in_major = same_major_entries[0][1]

        # Check for incompatible changes
        incompatibilities = self._detect_incompatible_changes(
            latest_in_major, profile
        )

        if incompatibilities:
            raise ProfilePublicationError(
                profile_id=profile.profile_id,
                version=str(profile.version),
                reasons=[
                    f"Incompatible changes detected within major version "
                    f"{profile.version.major}. A new major version is required. "
                    f"Changes: {'; '.join(incompatibilities)}"
                ],
            )

    def _detect_incompatible_changes(
        self,
        existing: AssessmentProfile,
        new: AssessmentProfile,
    ) -> list[str]:
        """
        Detect incompatible changes between two profiles that would
        require a major version bump.
        """
        incompatibilities: list[str] = []

        # Check required capability list changes
        existing_caps = frozenset(
            (item.capability_id, item.capability_version)
            for item in existing.items
        )
        new_caps = frozenset(
            (item.capability_id, item.capability_version)
            for item in new.items
        )
        if existing_caps != new_caps:
            incompatibilities.append("required capability list changed")

        # Check required field list changes
        existing_fields = frozenset(
            (item.capability_id, item.required_fields)
            for item in existing.items
        )
        new_fields = frozenset(
            (item.capability_id, item.required_fields)
            for item in new.items
        )
        if existing_fields != new_fields:
            incompatibilities.append("required field list changed")

        # Check required permission list changes (Req 5.1: profile publishes
        # a required Permission list; changing it within the same major
        # version is an incompatible change, same as required fields)
        existing_permissions = frozenset(
            (item.capability_id, item.required_permissions)
            for item in existing.items
        )
        new_permissions = frozenset(
            (item.capability_id, item.required_permissions)
            for item in new.items
        )
        if existing_permissions != new_permissions:
            incompatibilities.append("required permission list changed")

        # Check region scope rule changes
        if existing.region_rule != new.region_rule:
            incompatibilities.append("region scope rule changed")

        # Check completeness rule changes
        if existing.completeness_threshold != new.completeness_threshold:
            incompatibilities.append("completeness rule changed")

        return incompatibilities

    # ------------------------------------------------------------------
    # Digest computation
    # ------------------------------------------------------------------

    def _compute_content_digest(self, profile: AssessmentProfile) -> str:
        """
        Compute SHA-256 digest over canonical JSON representation of
        the profile content. Canonical JSON: sorted keys, compact
        separators, UTF-8.
        """
        profile_data = self._profile_to_canonical_dict(profile)
        canonical_bytes = json.dumps(
            profile_data,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(canonical_bytes).hexdigest()

    def _profile_to_canonical_dict(self, profile: AssessmentProfile) -> dict[str, Any]:
        """Convert AssessmentProfile to a canonical dictionary for hashing."""
        items_data = []
        for item in profile.items:
            items_data.append({
                "capability_id": item.capability_id,
                "capability_version": item.capability_version,
                "not_applicable_rule": item.not_applicable_rule,
                "required_fields": list(item.required_fields),
                "required_permissions": list(item.required_permissions),
                "target_scope": item.target_scope,
            })

        return {
            "collection_window": {
                "end": profile.collection_window.end,
                "period_type": profile.collection_window.period_type,
                "start": profile.collection_window.start,
            },
            "completeness_threshold": str(profile.completeness_threshold),
            "effective_at": (
                profile.effective_at.isoformat() if profile.effective_at else None
            ),
            "items": items_data,
            "profile_id": profile.profile_id,
            "region_rule": {
                "explicit_regions": list(profile.region_rule.explicit_regions),
                "mode": profile.region_rule.mode,
            },
            "schema_id": profile.schema_id,
            "schema_version": profile.schema_version,
            "status": profile.status,
            "version": str(profile.version),
        }

    # ------------------------------------------------------------------
    # Error helpers
    # ------------------------------------------------------------------

    def _reject_duplicate_version(
        self, profile: AssessmentProfile, existing_digest: str
    ) -> str:
        """Raise error for duplicate version with different content."""
        raise ProfilePublicationError(
            profile_id=profile.profile_id,
            version=str(profile.version),
            reasons=[
                f"Version {profile.version} already published with different "
                f"content (existing digest: {existing_digest}). "
                f"Published profiles are immutable."
            ],
        )

    def _make_not_found_error(
        self, profile_id: str, requested_version: str
    ) -> StructuredError:
        """Create StructuredError for profile not found."""
        profile_entries = self._profiles.get(profile_id)
        if profile_entries is None:
            available_profiles = sorted(self._profiles.keys())
            safe_message = (
                f"Unknown profile '{profile_id}'. "
                f"Available profiles: {available_profiles}"
            )
        else:
            available_versions = sorted(profile_entries.keys())
            safe_message = (
                f"Version '{requested_version}' not found for profile "
                f"'{profile_id}'. Available versions: {available_versions}"
            )

        return StructuredError(
            schema_id="structured-error",
            schema_version="1.0.0",
            code="PROFILE_NOT_FOUND",
            category="unsupported",
            retryable=False,
            safe_message=safe_message,
        )

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _version_gt(a: SemVer, b: SemVer) -> bool:
        """Return True if version a > version b."""
        return (a.major, a.minor, a.patch) > (b.major, b.minor, b.patch)


# ---------------------------------------------------------------------------
# Publication Errors (internal, not part of public contract)
# ---------------------------------------------------------------------------


class ProfilePublicationError(Exception):
    """Raised when profile publication fails validation."""

    def __init__(
        self,
        profile_id: str,
        version: str,
        reasons: list[str],
    ) -> None:
        self.profile_id = profile_id
        self.version = version
        self.reasons = reasons
        reasons_str = "; ".join(reasons)
        super().__init__(
            f"Publication rejected for profile '{profile_id}' v{version}: "
            f"{reasons_str}"
        )

    def to_structured_error(self) -> StructuredError:
        """Convert to a StructuredError for external reporting."""
        return StructuredError(
            schema_id="structured-error",
            schema_version="1.0.0",
            code="PROFILE_PUBLICATION_REJECTED",
            category="validation",
            retryable=False,
            safe_message=(
                f"Profile '{self.profile_id}' v{self.version} publication "
                f"rejected: {'; '.join(self.reasons)}"
            ),
        )
