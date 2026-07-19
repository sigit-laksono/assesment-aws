"""
Capability Registry — Immutable Manifest Discovery and Resolution.

Implements the CapabilityRegistry Protocol with:
- Startup-time registration with duplicate (capability_id, major_version) rejection (Req 1.2)
- Prerequisite DAG validation (acyclic graph) at registration
- Lifecycle metadata validation for deprecated/removed capabilities (Req 1.4)
- Exact version resolution and major-compatible resolution (Req 2.5)
- Immutable snapshot with canonical ordering (Req 1.3)
- SHA-256 manifest digest over canonical JSON
- discover() returns manifest without AWS session creation (Req 16.3)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from agentic.interfaces import Collector
from agentic.models import (
    CapabilityDescriptor,
    CapabilityManifest,
    SemVer,
    StructuredError,
)


@dataclass(frozen=True)
class RegisteredCapability:
    """A registered capability entry binding a descriptor to its handler."""

    descriptor: CapabilityDescriptor
    handler: Collector


class CapabilityRegistryImpl:
    """
    Concrete implementation of the CapabilityRegistry Protocol.

    Registration is startup-time only. Duplicate (capability_id, major_version)
    is rejected. A resolved snapshot is immutable for the lifetime of a run
    and receives a manifest digest. Removal is refused unless lifecycle metadata
    records replacement and support end date.
    """

    def __init__(self) -> None:
        # Internal storage: capability_id -> {major_version -> RegisteredCapability}
        self._entries: dict[str, dict[int, RegisteredCapability]] = {}
        # Cached snapshot (invalidated on registration)
        self._cached_snapshot: CapabilityManifest | None = None

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self, descriptor: CapabilityDescriptor, handler: Any
    ) -> None:
        """
        Register a capability with its handler.

        Validates:
        - Handler implements Collector protocol (has 'collect' method)
        - No duplicate (capability_id, major_version)
        - Lifecycle metadata for deprecated/removed capabilities
        - Prerequisite DAG: all prerequisites registered, no cycles
        """
        # Validate handler is a Collector (has collect method, not a bare function)
        if not hasattr(handler, "collect") or not callable(getattr(handler, "collect")):
            raise RegistrationError(
                f"Handler for '{descriptor.capability_id}' must implement the "
                f"Collector protocol with a 'collect' method. "
                f"Bare functions returning boolean are invalid."
            )

        # Validate lifecycle metadata for deprecated/removed capabilities (Req 1.4)
        if descriptor.support_status in ("deprecated", "removed"):
            if descriptor.lifecycle is None:
                raise RegistrationError(
                    f"Capability '{descriptor.capability_id}' has support_status "
                    f"'{descriptor.support_status}' but lifecycle metadata is missing. "
                    f"Deprecated/removed capabilities require replacement_capability_id "
                    f"and support_end_date."
                )
            if not descriptor.lifecycle.replacement_capability_id:
                raise RegistrationError(
                    f"Capability '{descriptor.capability_id}' has support_status "
                    f"'{descriptor.support_status}' but lifecycle metadata is missing "
                    f"replacement_capability_id."
                )
            if not descriptor.lifecycle.support_end_date:
                raise RegistrationError(
                    f"Capability '{descriptor.capability_id}' has support_status "
                    f"'{descriptor.support_status}' but lifecycle metadata is missing "
                    f"support_end_date."
                )

        # Reject duplicate (capability_id, major_version) (Req 1.2)
        cap_id = descriptor.capability_id
        major = descriptor.version.major
        if cap_id in self._entries and major in self._entries[cap_id]:
            existing = self._entries[cap_id][major].descriptor
            raise DuplicateCapabilityError(
                capability_id=cap_id,
                major_version=major,
                existing_version=str(existing.version),
                new_version=str(descriptor.version),
            )

        # Validate prerequisites: all declared prerequisites must be registered
        for prereq_id in descriptor.prerequisites:
            if prereq_id not in self._entries:
                raise RegistrationError(
                    f"Prerequisite '{prereq_id}' for capability "
                    f"'{cap_id}' is not registered."
                )

        # Validate no cycles in prerequisite DAG
        if self._would_create_cycle(cap_id, descriptor.prerequisites):
            raise RegistrationError(
                f"Adding capability '{cap_id}' would create a cycle "
                f"in the prerequisite dependency graph."
            )

        # Register the capability
        if cap_id not in self._entries:
            self._entries[cap_id] = {}
        self._entries[cap_id][major] = RegisteredCapability(
            descriptor=descriptor, handler=handler
        )

        # Invalidate cached snapshot
        self._cached_snapshot = None

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def resolve(
        self, capability_id: str, contract_version: str
    ) -> RegisteredCapability | StructuredError:
        """
        Resolve a registered capability by exact version match.
        Returns StructuredError with code 'UNSUPPORTED_CAPABILITY' if not found.
        """
        version = SemVer.parse(contract_version)
        entries = self._entries.get(capability_id)

        if entries is None:
            return self._make_unsupported_error(capability_id, contract_version)

        entry = entries.get(version.major)
        if entry is None:
            return self._make_unsupported_error(capability_id, contract_version)

        # Exact version match required
        desc_ver = entry.descriptor.version
        if (
            desc_ver.major == version.major
            and desc_ver.minor == version.minor
            and desc_ver.patch == version.patch
        ):
            return entry

        return self._make_unsupported_error(capability_id, contract_version)

    def resolve_compatible(
        self, capability_id: str, major_version: int
    ) -> RegisteredCapability | StructuredError:
        """
        Resolve the latest minor/patch within the same major version.
        Returns StructuredError if not found.
        """
        entries = self._entries.get(capability_id)

        if entries is None:
            return self._make_unsupported_error(
                capability_id, f"{major_version}.x.x"
            )

        entry = entries.get(major_version)
        if entry is None:
            return self._make_unsupported_error(
                capability_id, f"{major_version}.x.x"
            )

        return entry

    # ------------------------------------------------------------------
    # Snapshot and Discovery
    # ------------------------------------------------------------------

    def snapshot(self) -> CapabilityManifest:
        """
        Return the current immutable manifest snapshot with digest.
        Canonical ordering: (capability_id, major, minor, patch).
        Same content always produces the same digest (Req 1.3).
        """
        if self._cached_snapshot is not None:
            return self._cached_snapshot

        # Collect all descriptors
        descriptors: list[CapabilityDescriptor] = []
        for cap_entries in self._entries.values():
            for entry in cap_entries.values():
                descriptors.append(entry.descriptor)

        # Sort by canonical ordering: (capability_id, major, minor, patch)
        descriptors.sort(
            key=lambda d: (
                d.capability_id,
                d.version.major,
                d.version.minor,
                d.version.patch,
            )
        )

        # Compute manifest digest over canonical JSON
        digest = self._compute_manifest_digest(tuple(descriptors))

        manifest = CapabilityManifest(
            schema_id="capability-manifest",
            schema_version="1.0.0",
            capabilities=tuple(descriptors),
            manifest_digest=digest,
        )

        self._cached_snapshot = manifest
        return manifest

    def discover(self) -> CapabilityManifest:
        """
        Return the machine-readable manifest without creating AWS sessions.
        Identical to snapshot() — this method makes explicit that no AWS
        session is created (Req 16.3).
        """
        return self.snapshot()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _would_create_cycle(
        self, new_cap_id: str, prerequisites: tuple[str, ...]
    ) -> bool:
        """
        Check if adding new_cap_id with the given prerequisites would
        create a cycle in the prerequisite DAG.

        A cycle exists if any transitive prerequisite of new_cap_id's
        prerequisites eventually reaches new_cap_id.
        """
        if not prerequisites:
            return False

        # BFS/DFS from each prerequisite — if we reach new_cap_id, there's a cycle
        visited: set[str] = set()
        stack = list(prerequisites)

        while stack:
            current = stack.pop()
            if current == new_cap_id:
                return True
            if current in visited:
                continue
            visited.add(current)

            # Get prerequisites of current capability
            if current in self._entries:
                for entry in self._entries[current].values():
                    for prereq in entry.descriptor.prerequisites:
                        if prereq not in visited:
                            stack.append(prereq)

        return False

    def _compute_manifest_digest(
        self, descriptors: tuple[CapabilityDescriptor, ...]
    ) -> str:
        """
        Compute SHA-256 digest over canonical JSON representation of the manifest.
        Canonical JSON: sorted keys, compact separators, UTF-8.
        """
        # Build a serializable representation
        capabilities_data = []
        for desc in descriptors:
            cap_data: dict[str, Any] = {
                "capability_id": desc.capability_id,
                "version": str(desc.version),
                "input_schema_ref": desc.input_schema_ref,
                "output_schema_ref": desc.output_schema_ref,
                "error_schema_ref": desc.error_schema_ref,
                "permissions": list(desc.permissions),
                "allowed_operations": list(desc.allowed_operations),
                "prerequisites": list(desc.prerequisites),
                "support_status": desc.support_status,
                "scope": desc.scope,
            }
            if desc.lifecycle is not None:
                cap_data["lifecycle"] = {
                    "replacement_capability_id": desc.lifecycle.replacement_capability_id,
                    "support_end_date": desc.lifecycle.support_end_date,
                    "deprecation_reason": desc.lifecycle.deprecation_reason,
                }
            else:
                cap_data["lifecycle"] = None
            capabilities_data.append(cap_data)

        manifest_data = {
            "schema_id": "capability-manifest",
            "schema_version": "1.0.0",
            "capabilities": capabilities_data,
        }

        canonical_bytes = json.dumps(
            manifest_data,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

        return hashlib.sha256(canonical_bytes).hexdigest()

    def _make_unsupported_error(
        self, capability_id: str, requested_version: str
    ) -> StructuredError:
        """
        Create a StructuredError for unsupported capability/version,
        listing supported versions (Req 2.5).
        """
        entries = self._entries.get(capability_id)
        if entries is None:
            supported_capabilities = sorted(self._entries.keys())
            safe_message = (
                f"Unknown capability '{capability_id}'. "
                f"Supported capabilities: {supported_capabilities}"
            )
        else:
            supported_versions = [
                str(entry.descriptor.version)
                for entry in sorted(
                    entries.values(),
                    key=lambda e: (
                        e.descriptor.version.major,
                        e.descriptor.version.minor,
                        e.descriptor.version.patch,
                    ),
                )
            ]
            safe_message = (
                f"Unsupported version '{requested_version}' for capability "
                f"'{capability_id}'. Supported versions: {supported_versions}"
            )

        return StructuredError(
            schema_id="structured-error",
            schema_version="1.0.0",
            code="UNSUPPORTED_CAPABILITY",
            category="unsupported",
            retryable=False,
            safe_message=safe_message,
            capability_id=capability_id,
        )


# ---------------------------------------------------------------------------
# Registration Errors (internal, not part of public contract)
# ---------------------------------------------------------------------------


class RegistrationError(Exception):
    """Raised when capability registration fails validation."""

    pass


class DuplicateCapabilityError(RegistrationError):
    """Raised when a duplicate (capability_id, major_version) is registered."""

    def __init__(
        self,
        capability_id: str,
        major_version: int,
        existing_version: str,
        new_version: str,
    ) -> None:
        self.capability_id = capability_id
        self.major_version = major_version
        self.existing_version = existing_version
        self.new_version = new_version
        super().__init__(
            f"Duplicate registration rejected: capability '{capability_id}' "
            f"major version {major_version} already registered as "
            f"v{existing_version}. Attempted: v{new_version}."
        )

    def to_structured_error(self) -> StructuredError:
        """Convert to a StructuredError for external reporting (Req 1.2)."""
        return StructuredError(
            schema_id="structured-error",
            schema_version="1.0.0",
            code="DUPLICATE_CAPABILITY",
            category="conflict",
            retryable=False,
            safe_message=(
                f"Capability '{self.capability_id}' with major version "
                f"{self.major_version} is already registered (v{self.existing_version}). "
                f"Cannot register v{self.new_version}."
            ),
            capability_id=self.capability_id,
        )
