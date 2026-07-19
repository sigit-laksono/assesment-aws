"""
Agentic AWS Assessment — Contract Layer.

This package defines the versioned domain models and protocol interfaces
for the agentic assessment system. All persisted models carry a schema_id
and exact schema_version. Internal exceptions are NOT part of this public
contract.
"""

from agentic.models import (
    SemVer,
    SchemaViolation,
    ValidationResult,
    StructuredError,
    CapabilityRequest,
    AccountTarget,
    ExecutionContext,
    InvocationRequest,
    CapabilityDescriptor,
    LifecycleMetadata,
    CapabilityManifest,
    RegionRule,
    CollectionWindow,
    RequiredProfileItem,
    AssessmentProfile,
    ExecutionUnit,
    ExecutionPlan,
    ResourceRecord,
    Evidence,
    CollectorOutcome,
    UnitResult,
    CapabilitySummary,
    CompletenessItem,
    CompletenessReport,
    InvocationResult,
    PermissionResult,
    PermissionReport,
    IdempotencyRecord,
    HistoryEntry,
    ResourceDelta,
    CompletenessDelta,
    TargetPair,
    DriftReport,
    TelemetryEvent,
)

from agentic.interfaces import (
    SchemaProcessor,
    CapabilityRegistry,
    AssessmentProfileRegistry,
    Collector,
    EvidenceStore,
    HistoryStore,
    SessionFactory,
    GuardedSession,
    TelemetryService,
)

from agentic.orchestrator import invoke
from agentic.summary import summarize
from agentic.runs import list_runs

__all__ = [
    # Models
    "SemVer",
    "SchemaViolation",
    "ValidationResult",
    "StructuredError",
    "CapabilityRequest",
    "AccountTarget",
    "ExecutionContext",
    "InvocationRequest",
    "CapabilityDescriptor",
    "LifecycleMetadata",
    "CapabilityManifest",
    "RegionRule",
    "CollectionWindow",
    "RequiredProfileItem",
    "AssessmentProfile",
    "ExecutionUnit",
    "ExecutionPlan",
    "ResourceRecord",
    "Evidence",
    "CollectorOutcome",
    "UnitResult",
    "CapabilitySummary",
    "CompletenessItem",
    "CompletenessReport",
    "InvocationResult",
    "PermissionResult",
    "PermissionReport",
    "IdempotencyRecord",
    "HistoryEntry",
    "ResourceDelta",
    "CompletenessDelta",
    "TargetPair",
    "DriftReport",
    "TelemetryEvent",
    # Interfaces
    "SchemaProcessor",
    "CapabilityRegistry",
    "AssessmentProfileRegistry",
    "Collector",
    "EvidenceStore",
    "HistoryStore",
    "SessionFactory",
    "GuardedSession",
    "TelemetryService",
    # Public API
    "invoke",
    "summarize",
    "list_runs",
]
