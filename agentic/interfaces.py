"""
Agentic AWS Assessment — Protocol Interfaces.

These Protocol classes define the injectable boundaries for the agentic
assessment system. Components can be injected and tested offline without
AWS access or live infrastructure.

Internal exceptions are NOT part of these public contracts.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence

from agentic.models import (
    AccountTarget,
    AssessmentProfile,
    CapabilityManifest,
    CollectorOutcome,
    DriftReport,
    Evidence,
    ExecutionPlan,
    HistoryEntry,
    IdempotencyRecord,
    InvocationResult,
    PermissionReport,
    SemVer,
    TelemetryEvent,
    ValidationResult,
)


# ---------------------------------------------------------------------------
# Schema Processing (Req 3.1)
# ---------------------------------------------------------------------------


class SchemaProcessor(Protocol):
    """
    Validates, parses, serializes, and canonicalizes payloads against
    versioned schemas from the Schema Catalog.
    """

    def validate(
        self, schema_id: str, version: str, payload: Mapping[str, Any]
    ) -> ValidationResult:
        """Validate payload against the declared schema version."""
        ...

    def canonical_bytes(
        self, schema_id: str, version: str, payload: Mapping[str, Any]
    ) -> bytes:
        """Serialize a valid payload as deterministic Canonical JSON bytes."""
        ...

    def parse(
        self, schema_id: str, version: str, data: bytes
    ) -> Mapping[str, Any]:
        """Parse serialized Canonical JSON back into a mapping."""
        ...


# ---------------------------------------------------------------------------
# Capability Registry (Req 1)
# ---------------------------------------------------------------------------


class CapabilityRegistry(Protocol):
    """
    Stores the Capability Manifest and maps capability IDs to executable
    implementations. Registration is startup-time only.
    """

    def snapshot(self) -> CapabilityManifest:
        """Return the current immutable manifest snapshot with digest."""
        ...

    def resolve(
        self, capability_id: str, contract_version: str
    ) -> Any:
        """
        Resolve a registered capability by ID and version.
        Returns the registered capability entry (implementation-defined type).
        Raises or returns error for unsupported/unresolved capabilities.
        """
        ...


# ---------------------------------------------------------------------------
# Assessment Profile Registry (Req 5)
# ---------------------------------------------------------------------------


class AssessmentProfileRegistry(Protocol):
    """
    Stores, validates, and resolves Assessment Profiles by identifier
    and Semantic Version. Published profiles are immutable.
    """

    def resolve(
        self, profile_id: str, version: str
    ) -> AssessmentProfile:
        """
        Resolve an exact profile version. Returns immutable profile content.
        """
        ...

    def resolve_compatible(
        self, profile_id: str, major_version: int
    ) -> AssessmentProfile:
        """
        Resolve the latest profile compatible with the given major version.
        Only allowed for interactive/agent invocations; scheduled runs
        require exact version.
        """
        ...

    def publish(self, profile: AssessmentProfile) -> str:
        """
        Publish a profile version. Returns the content digest.
        Rejects publication if version already exists with different content.
        """
        ...


# ---------------------------------------------------------------------------
# Collector (Req 4, 8, 9)
# ---------------------------------------------------------------------------


class Collector(Protocol):
    """
    Contract Collector that returns a typed CollectorOutcome.
    A bare boolean is invalid. Collectors do not mutate shared state.
    """

    def collect(
        self,
        capability_id: str,
        capability_version: str,
        account_id: str,
        region_scope: str,
        parameters: Mapping[str, Any],
        session: Any,
    ) -> CollectorOutcome:
        """
        Execute collection for one capability against one target.
        Returns structured outcome with records, evidence, and error.
        """
        ...


# ---------------------------------------------------------------------------
# Store Interfaces (Req 8, 12)
# ---------------------------------------------------------------------------


class EvidenceStore(Protocol):
    """
    Persists and retrieves Evidence with integrity verification.
    """

    def store(
        self, run_id: str, unit_id: str, evidence: Sequence[Evidence]
    ) -> None:
        """Store evidence records for a unit within a run."""
        ...

    def retrieve(
        self, run_id: str, unit_id: str
    ) -> tuple[Evidence, ...]:
        """Retrieve evidence for a unit. Returns content with verifiable digest."""
        ...

    def verify_integrity(self, run_id: str) -> bool:
        """Verify content digests match stored evidence for a run."""
        ...


class HistoryStore(Protocol):
    """
    Durable assessment history with indexed querying and retention.
    """

    def commit(self, entry: HistoryEntry, result: InvocationResult) -> None:
        """Persist a terminal run as one indexed history entry."""
        ...

    def query(
        self,
        account_id: str | None = None,
        time_start: str | None = None,
        time_end: str | None = None,
        profile_id: str | None = None,
        profile_version: str | None = None,
        status: str | None = None,
        capability_id: str | None = None,
        order: str = "asc",
    ) -> tuple[HistoryEntry, ...]:
        """
        Query history entries with AND-combined filters.
        Order by (collection_time, run_id) in the specified direction.
        """
        ...

    def get_result(self, run_id: str) -> InvocationResult | None:
        """Retrieve a persisted result whose digest matches the stored digest."""
        ...


# ---------------------------------------------------------------------------
# Session and Security (Req 10, 11)
# ---------------------------------------------------------------------------


class GuardedSession(Protocol):
    """
    Session boundary that intercepts every SDK operation and checks it
    against the resolved capability allowlist before dispatch.
    """

    def call(
        self, service: str, operation: str, **kwargs: Any
    ) -> Any:
        """
        Execute an AWS SDK operation only if it appears in the allowlist.
        Unknown or non-member operations fail closed.
        """
        ...


class SessionFactory(Protocol):
    """
    Creates guarded sessions per account. Persisted requests contain no
    access key, secret, or session token.
    """

    def for_account(self, target: AccountTarget) -> GuardedSession:
        """
        Create a guarded session for the specified account target.
        Uses ambient credentials or declared role reference.
        """
        ...


# ---------------------------------------------------------------------------
# Telemetry (Req 14)
# ---------------------------------------------------------------------------


class TelemetryService(Protocol):
    """
    Emits structured JSON telemetry events. Compatible with Python logging.
    Sensitive and unbounded resource values are excluded.
    """

    def emit(self, event: TelemetryEvent) -> None:
        """Emit a single telemetry event."""
        ...

    def query_by_correlation(
        self, correlation_id: str
    ) -> tuple[TelemetryEvent, ...]:
        """Retrieve all retained events for a correlation ID."""
        ...
