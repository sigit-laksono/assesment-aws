"""
Agentic AWS Assessment — Immutable Domain Models.

All persisted models carry `schema_id` and exact `schema_version` (Semantic Version).
Models use frozen dataclasses for immutability. Identifiers are non-secret
strings with bounded length. Timestamps are RFC 3339 UTC with 'Z'.
Monetary values serialize as decimal strings.

Internal exceptions are NOT part of this public contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Mapping


# ---------------------------------------------------------------------------
# Value Objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SemVer:
    """Semantic Version identifier (major.minor.patch)."""

    major: int
    minor: int
    patch: int

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    @classmethod
    def parse(cls, version_str: str) -> "SemVer":
        """Parse a 'major.minor.patch' string into a SemVer instance."""
        parts = version_str.strip().split(".")
        if len(parts) != 3:
            raise ValueError(
                f"Invalid semantic version format: '{version_str}'. "
                "Expected 'major.minor.patch'."
            )
        return cls(major=int(parts[0]), minor=int(parts[1]), patch=int(parts[2]))


@dataclass(frozen=True)
class TargetPair:
    """Combination of one AWS Account and one AWS Region (or 'aws-global')."""

    account_id: str
    region_scope: str


# ---------------------------------------------------------------------------
# Schema and Validation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SchemaViolation:
    """A single schema validation violation."""

    json_path: str
    constraint: str
    safe_message: str


@dataclass(frozen=True)
class ValidationResult:
    """Result of schema validation — violations list and truncation flag."""

    violations: tuple[SchemaViolation, ...] = ()
    report_truncated: bool = False

    @property
    def is_valid(self) -> bool:
        return len(self.violations) == 0


# ---------------------------------------------------------------------------
# StructuredError (Req 9.4)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StructuredError:
    """
    Structured Error containing capability ID, Target Pair, error category,
    retryability, and secret-free message. (Requirement 9.4)

    Exceptions and AWS error objects are never persisted directly. This model
    is the public contract representation for all error conditions.
    """

    schema_id: str = "structured-error"
    schema_version: str = "1.0.0"
    code: str = ""
    category: Literal[
        "validation",
        "unsupported",
        "permission-denied",
        "throttled",
        "transient",
        "guard-violation",
        "internal",
        "conflict",
    ] = "internal"
    retryable: bool = False
    safe_message: str = ""
    capability_id: str | None = None
    account_id: str | None = None
    region_scope: str | None = None
    violations: tuple[SchemaViolation, ...] = ()


# ---------------------------------------------------------------------------
# Invocation Request (Req 2.1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CapabilityRequest:
    """A single capability selection within an Invocation Request."""

    id: str
    version: str
    parameters: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AccountTarget:
    """An AWS Account target with an optional role reference."""

    account_id: str
    role_ref: str | None = None


@dataclass(frozen=True)
class ExecutionContext:
    """
    Execution Context: caller identity, correlation ID, Idempotency Key,
    purpose, and timeout.
    """

    caller_id: str
    correlation_id: str
    idempotency_key: str | None = None
    purpose: str = ""
    timeout_seconds: int = 3600


@dataclass(frozen=True)
class InvocationRequest:
    """
    Versioned Invocation Request payload. Exactly one of `capabilities` or
    `profile` is required. Credential values are prohibited.
    """

    schema_id: str = "invocation-request"
    schema_version: str = "1.0.0"
    capabilities: tuple[CapabilityRequest, ...] | None = None
    profile: str | None = None
    targets: tuple[AccountTarget, ...] = ()
    regions: tuple[str, ...] = ()
    execution_context: ExecutionContext | None = None


# ---------------------------------------------------------------------------
# Capability Registry Models (Req 1, 3.1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LifecycleMetadata:
    """Lifecycle metadata for deprecated/removed capabilities."""

    replacement_capability_id: str | None = None
    support_end_date: str | None = None
    deprecation_reason: str = ""


@dataclass(frozen=True)
class CapabilityDescriptor:
    """
    Frozen capability descriptor within the registry.
    Registration is startup-time only.
    """

    schema_id: str = "capability-descriptor"
    schema_version: str = "1.0.0"
    capability_id: str = ""
    version: SemVer = field(default_factory=lambda: SemVer(0, 0, 0))
    input_schema_ref: str = ""
    output_schema_ref: str = ""
    error_schema_ref: str = ""
    permissions: tuple[str, ...] = ()
    allowed_operations: tuple[str, ...] = ()
    prerequisites: tuple[str, ...] = ()
    support_status: Literal["active", "deprecated", "removed"] = "active"
    lifecycle: LifecycleMetadata | None = None
    scope: Literal["global", "regional", "derived"] = "regional"


@dataclass(frozen=True)
class CapabilityManifest:
    """
    Immutable snapshot of all registered capabilities with a content digest.
    """

    schema_id: str = "capability-manifest"
    schema_version: str = "1.0.0"
    capabilities: tuple[CapabilityDescriptor, ...] = ()
    manifest_digest: str = ""


# ---------------------------------------------------------------------------
# Assessment Profile Models (Req 5)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegionRule:
    """Region applicability rule for an Assessment Profile."""

    mode: Literal["explicit", "discovery", "global-only"] = "explicit"
    explicit_regions: tuple[str, ...] = ()


@dataclass(frozen=True)
class CollectionWindow:
    """Collection window definition (UTC-based)."""

    period_type: Literal["monthly", "weekly", "daily", "custom"] = "monthly"
    start: str = ""  # RFC 3339 UTC
    end: str = ""  # RFC 3339 UTC


@dataclass(frozen=True)
class RequiredProfileItem:
    """
    Combination of capability, field set, target applicability,
    required permissions, and completeness behavior.
    """

    capability_id: str = ""
    capability_version: str = ""
    required_fields: tuple[str, ...] = ()
    target_scope: Literal["global", "regional", "derived"] = "regional"
    required_permissions: tuple[str, ...] = ()
    not_applicable_rule: str | None = None


@dataclass(frozen=True)
class AssessmentProfile:
    """
    Frozen Assessment Profile. Published versions are immutable and
    content-addressed.
    """

    schema_id: str = "assessment-profile"
    schema_version: str = "1.0.0"
    profile_id: str = ""
    version: SemVer = field(default_factory=lambda: SemVer(0, 0, 0))
    effective_at: datetime | None = None
    status: Literal["draft", "active", "retired"] = "draft"
    items: tuple[RequiredProfileItem, ...] = ()
    region_rule: RegionRule = field(default_factory=RegionRule)
    collection_window: CollectionWindow = field(default_factory=CollectionWindow)
    completeness_threshold: Decimal = Decimal("1.0")
    manifest_digest: str = ""


# ---------------------------------------------------------------------------
# Execution Plan Models (Req 6)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExecutionUnit:
    """
    One identifiable work item: one Capability against one Target Pair.
    """

    unit_id: str = ""
    ordinal: int = 0
    capability_id: str = ""
    capability_version: str = ""
    account_id: str = ""
    region_scope: str = ""
    parameters: Mapping[str, Any] = field(default_factory=dict)
    prerequisite_unit_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExecutionPlan:
    """
    Immutable ordered Execution Plan. Contains no session, secret,
    timestamp, or callable.
    """

    schema_id: str = "execution-plan"
    schema_version: str = "1.0.0"
    request_digest: str = ""
    manifest_digest: str = ""
    profile_digest: str | None = None
    region_discovery_snapshot: Mapping[str, tuple[str, ...]] = field(
        default_factory=dict
    )
    units: tuple[ExecutionUnit, ...] = ()
    plan_digest: str = ""


# ---------------------------------------------------------------------------
# Collector Outcome and Evidence (Req 8, 9)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResourceRecord:
    """
    Collected resource record with stable identity, schema fields,
    and provenance reference.
    """

    resource_identity: str = ""
    account_id: str = ""
    region_scope: str = ""
    capability_id: str = ""
    fields: Mapping[str, Any] = field(default_factory=dict)
    provenance_ref: str = ""


@dataclass(frozen=True)
class Evidence:
    """
    Evidence linking a collected record to its source.
    """

    schema_id: str = "evidence"
    schema_version: str = "1.0.0"
    target: TargetPair = field(default_factory=lambda: TargetPair("", ""))
    capability_id: str = ""
    capability_version: str = ""
    collector_version: str = ""
    operation: str = ""
    collected_at: str = ""  # RFC 3339 UTC with 'Z'
    run_id: str = ""
    unit_id: str = ""
    transformation_chain: tuple[str, ...] = ()
    content_digest: str = ""


@dataclass(frozen=True)
class CollectorOutcome:
    """
    Typed outcome from a Collector execution. A successful empty result
    is `succeeded` with zero records, never False.
    """

    status: Literal["succeeded", "failed"] = "succeeded"
    records: tuple[ResourceRecord, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    error: StructuredError | None = None
    attempts: int = 1


# ---------------------------------------------------------------------------
# Invocation Result (Req 9.1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UnitResult:
    """Per-execution-unit outcome within an Invocation Result."""

    unit_id: str = ""
    capability_id: str = ""
    account_id: str = ""
    region_scope: str = ""
    status: Literal["succeeded", "failed"] = "succeeded"
    records_count: int = 0
    error: StructuredError | None = None
    attempts: int = 1


@dataclass(frozen=True)
class CapabilitySummary:
    """
    Per-capability, per-target outcome count (Requirement 12.1). A
    succeeded call with zero records stays "succeeded" (Requirement 12.2).
    """

    capability_id: str = ""
    account_id: str = ""
    region_scope: str = ""
    status: Literal["succeeded", "failed", "permission-denied"] = "succeeded"
    record_count: int = 0


@dataclass(frozen=True)
class CompletenessItem:
    """
    One completeness row keyed by (account_id, region_scope, capability_id,
    required_item_id).
    """

    account_id: str = ""
    region_scope: str = ""
    capability_id: str = ""
    required_item_id: str = ""
    status: Literal[
        "completed",
        "completed-empty",
        "failed",
        "permission-denied",
        "unsupported",
        "not-applicable",
    ] = "completed"
    governing_rule: str | None = None
    error_ref: str | None = None


@dataclass(frozen=True)
class CompletenessReport:
    """
    Machine-readable completeness report. Category totals equal the
    applicable required-item count; ratio = completed / applicable.
    """

    schema_id: str = "completeness-report"
    schema_version: str = "1.0.0"
    items: tuple[CompletenessItem, ...] = ()
    total_applicable: int = 0
    total_completed: int = 0
    total_completed_empty: int = 0
    total_failed: int = 0
    total_permission_denied: int = 0
    total_unsupported: int = 0
    total_not_applicable: int = 0
    ratio: Decimal = Decimal("0")


@dataclass(frozen=True)
class InvocationResult:
    """
    Versioned Invocation Result payload containing status, data,
    error, Evidence, and execution metadata.
    """

    schema_id: str = "invocation-result"
    schema_version: str = "1.0.0"
    run_id: str = ""
    correlation_id: str = ""
    execution_status: Literal[
        "succeeded", "partial-success", "failed", "cancelled"
    ] = "succeeded"
    completeness_status: Literal[
        "complete", "incomplete", "not-evaluated"
    ] = "not-evaluated"
    request_digest: str = ""
    plan_digest: str = ""
    profile_id: str | None = None
    profile_version: str | None = None
    manifest_version: str = ""
    unit_results: tuple[UnitResult, ...] = ()
    capability_summaries: tuple[CapabilitySummary, ...] = ()
    completeness: CompletenessReport | None = None
    started_at: str = ""  # RFC 3339 UTC with 'Z'
    completed_at: str = ""  # RFC 3339 UTC with 'Z'


# ---------------------------------------------------------------------------
# Permission Report (Req 10)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PermissionResult:
    """
    One permission classification per (target scope, permission).
    """

    target: TargetPair = field(default_factory=lambda: TargetPair("", ""))
    permission: str = ""
    classification: Literal[
        "available", "unavailable", "indeterminate"
    ] = "indeterminate"
    affected_capabilities: tuple[str, ...] = ()
    affected_items: tuple[str, ...] = ()
    evidence_method: Literal[
        "dry-run", "simulation", "runtime", "unverifiable"
    ] = "unverifiable"
    safe_reason: str = ""


@dataclass(frozen=True)
class PermissionReport:
    """Permission preflight report for all targets and permissions."""

    schema_id: str = "permission-report"
    schema_version: str = "1.0.0"
    results: tuple[PermissionResult, ...] = ()


# ---------------------------------------------------------------------------
# Idempotency (Req 7)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IdempotencyRecord:
    """
    Binds an idempotency key to a request digest and run ID.
    """

    key: str = ""
    request_digest: str = ""
    run_id: str = ""
    state: Literal["active", "completed", "failed"] = "active"
    created_at: str = ""  # RFC 3339 UTC with 'Z'
    updated_at: str = ""  # RFC 3339 UTC with 'Z'
    terminal_result_digest: str | None = None


# ---------------------------------------------------------------------------
# History (Req 12)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HistoryEntry:
    """
    Indexed history entry for a completed Assessment Run.
    """

    schema_id: str = "history-entry"
    schema_version: str = "1.0.0"
    run_id: str = ""
    account_ids: tuple[str, ...] = ()
    region_scopes: tuple[str, ...] = ()
    capability_ids: tuple[str, ...] = ()
    profile_id: str | None = None
    profile_version: str | None = None
    manifest_version: str = ""
    execution_status: str = ""
    collection_time: str = ""  # RFC 3339 UTC with 'Z'
    result_digest: str = ""


# ---------------------------------------------------------------------------
# Drift (Req 13)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResourceDelta:
    """A single resource difference between two runs."""

    capability_id: str = ""
    resource_identity: str = ""
    changed_fields: Mapping[str, tuple[Any, Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class CompletenessDelta:
    """Completeness difference for one item between two runs."""

    account_id: str = ""
    region_scope: str = ""
    capability_id: str = ""
    required_item_id: str = ""
    left_status: str = ""
    right_status: str = ""


@dataclass(frozen=True)
class DriftReport:
    """
    Version-aware drift report between two compatible completed runs.
    """

    schema_id: str = "drift-report"
    schema_version: str = "1.0.0"
    left_run_id: str = ""
    right_run_id: str = ""
    target_overlap: tuple[TargetPair, ...] = ()
    schema_versions: Mapping[str, tuple[str, str]] = field(default_factory=dict)
    profile_versions: tuple[str | None, str | None] = (None, None)
    added: tuple[ResourceDelta, ...] = ()
    removed: tuple[ResourceDelta, ...] = ()
    changed: tuple[ResourceDelta, ...] = ()
    unchanged_count: int = 0
    completeness_drift: tuple[CompletenessDelta, ...] = ()
    compared_at: str = ""  # RFC 3339 UTC with 'Z'


# ---------------------------------------------------------------------------
# Telemetry (Req 14)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TelemetryEvent:
    """
    Bounded telemetry event. Record bodies, tags, request parameters,
    role external IDs, and credentials are prohibited fields.
    """

    schema_id: str = "telemetry-event"
    schema_version: str = "1.0.0"
    event_name: str = ""
    timestamp: str = ""  # RFC 3339 UTC with 'Z'
    correlation_id: str = ""
    run_id: str = ""
    unit_id: str = ""
    previous_state: str | None = None
    current_state: str | None = None
    attempt: int = 0
    capability_id: str = ""
    profile_id: str = ""
    profile_version: str = ""
    account_id: str = ""
    region_scope: str = ""
    duration_ms: int | None = None
    record_count: int | None = None
    safe_error_code: str | None = None
