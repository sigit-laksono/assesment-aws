"""
Unit tests for agentic contract package — models and interfaces.
Verifies immutability, schema_id/schema_version presence, and Protocol compliance.
"""

from decimal import Decimal

import pytest

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


# ---------------------------------------------------------------------------
# SemVer tests
# ---------------------------------------------------------------------------


class TestSemVer:
    def test_parse_valid(self):
        v = SemVer.parse("1.2.3")
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3

    def test_str_representation(self):
        v = SemVer(major=2, minor=0, patch=1)
        assert str(v) == "2.0.1"

    def test_parse_invalid_format(self):
        with pytest.raises(ValueError):
            SemVer.parse("1.2")

    def test_parse_invalid_non_numeric(self):
        with pytest.raises(ValueError):
            SemVer.parse("a.b.c")

    def test_frozen(self):
        v = SemVer(1, 0, 0)
        with pytest.raises(Exception):
            v.major = 2  # type: ignore


# ---------------------------------------------------------------------------
# Persisted models carry schema_id and schema_version
# ---------------------------------------------------------------------------

PERSISTED_MODELS = [
    StructuredError,
    InvocationRequest,
    CapabilityDescriptor,
    CapabilityManifest,
    AssessmentProfile,
    ExecutionPlan,
    Evidence,
    CompletenessReport,
    InvocationResult,
    PermissionReport,
    HistoryEntry,
    DriftReport,
    TelemetryEvent,
]


@pytest.mark.parametrize("model_cls", PERSISTED_MODELS, ids=lambda c: c.__name__)
def test_persisted_model_has_schema_id_and_version(model_cls):
    """All persisted models must have non-empty schema_id and schema_version."""
    inst = model_cls()
    assert hasattr(inst, "schema_id")
    assert hasattr(inst, "schema_version")
    assert inst.schema_id != ""
    assert inst.schema_version != ""


# ---------------------------------------------------------------------------
# Immutability tests
# ---------------------------------------------------------------------------

FROZEN_MODELS = [
    (StructuredError, "code", "NEW"),
    (InvocationRequest, "schema_id", "X"),
    (CapabilityDescriptor, "capability_id", "X"),
    (CapabilityManifest, "manifest_digest", "X"),
    (AssessmentProfile, "profile_id", "X"),
    (ExecutionUnit, "unit_id", "X"),
    (ExecutionPlan, "plan_digest", "X"),
    (ResourceRecord, "resource_identity", "X"),
    (Evidence, "content_digest", "X"),
    (CollectorOutcome, "status", "failed"),
    (UnitResult, "unit_id", "X"),
    (CompletenessItem, "account_id", "X"),
    (CompletenessReport, "total_applicable", 99),
    (InvocationResult, "run_id", "X"),
    (PermissionResult, "permission", "X"),
    (PermissionReport, "schema_id", "X"),
    (IdempotencyRecord, "key", "X"),
    (HistoryEntry, "run_id", "X"),
    (ResourceDelta, "capability_id", "X"),
    (CompletenessDelta, "left_status", "X"),
    (TargetPair, "account_id", "X"),  # requires positional args
    (DriftReport, "left_run_id", "X"),
    (TelemetryEvent, "event_name", "X"),
]


@pytest.mark.parametrize("model_cls,attr,val", FROZEN_MODELS, ids=lambda x: x.__name__ if hasattr(x, "__name__") else str(x))
def test_model_is_frozen(model_cls, attr, val):
    """All domain models must be frozen (immutable)."""
    if model_cls is TargetPair:
        inst = TargetPair(account_id="123", region_scope="us-east-1")
    else:
        inst = model_cls()
    with pytest.raises(Exception):
        setattr(inst, attr, val)


# ---------------------------------------------------------------------------
# StructuredError contract (Req 9.4)
# ---------------------------------------------------------------------------


class TestStructuredError:
    def test_default_values(self):
        err = StructuredError()
        assert err.schema_id == "structured-error"
        assert err.schema_version == "1.0.0"
        assert err.category == "internal"
        assert err.retryable is False
        assert err.violations == ()

    def test_full_construction(self):
        err = StructuredError(
            code="E_VALIDATION_001",
            category="validation",
            retryable=False,
            safe_message="Invalid capability ID format",
            capability_id="ec2.inventory",
            account_id="123456789012",
            region_scope="ap-southeast-1",
            violations=(
                SchemaViolation(
                    json_path="$.capabilities[0].id",
                    constraint="pattern",
                    safe_message="Must match capability ID format",
                ),
            ),
        )
        assert err.code == "E_VALIDATION_001"
        assert len(err.violations) == 1


# ---------------------------------------------------------------------------
# InvocationRequest contract (Req 2.1)
# ---------------------------------------------------------------------------


class TestInvocationRequest:
    def test_with_explicit_capabilities(self):
        req = InvocationRequest(
            capabilities=(
                CapabilityRequest(id="ec2.inventory", version="1.0.0"),
            ),
            targets=(AccountTarget(account_id="123456789012", role_ref="role/key"),),
            regions=("ap-southeast-1",),
            execution_context=ExecutionContext(
                caller_id="agent/test",
                correlation_id="corr-001",
                idempotency_key="idem-001",
                purpose="monthly-assessment",
                timeout_seconds=3600,
            ),
        )
        assert req.schema_id == "invocation-request"
        assert req.capabilities is not None
        assert req.profile is None

    def test_with_profile_mode(self):
        req = InvocationRequest(
            profile="monthly-standard@1.0.0",
            targets=(AccountTarget(account_id="999888777666"),),
            regions=("us-east-1", "eu-west-1"),
        )
        assert req.capabilities is None
        assert req.profile == "monthly-standard@1.0.0"


# ---------------------------------------------------------------------------
# CollectorOutcome contract (Req 8, 9)
# ---------------------------------------------------------------------------


class TestCollectorOutcome:
    def test_successful_empty(self):
        outcome = CollectorOutcome(status="succeeded", records=(), evidence=())
        assert outcome.status == "succeeded"
        assert outcome.error is None
        assert outcome.attempts == 1

    def test_failed_with_error(self):
        outcome = CollectorOutcome(
            status="failed",
            error=StructuredError(
                code="E_PERM",
                category="permission-denied",
                safe_message="Access denied",
            ),
            attempts=3,
        )
        assert outcome.status == "failed"
        assert outcome.error is not None
        assert outcome.error.category == "permission-denied"


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------


class TestValidationResult:
    def test_valid(self):
        vr = ValidationResult()
        assert vr.is_valid is True

    def test_invalid(self):
        vr = ValidationResult(
            violations=(
                SchemaViolation(json_path="$.x", constraint="required", safe_message="missing"),
            )
        )
        assert vr.is_valid is False


# ---------------------------------------------------------------------------
# Protocol interface compliance (structural typing check)
# ---------------------------------------------------------------------------


class TestProtocolStructure:
    """Verify Protocol classes define expected methods."""

    def test_schema_processor_methods(self):
        assert hasattr(SchemaProcessor, "validate")
        assert hasattr(SchemaProcessor, "canonical_bytes")
        assert hasattr(SchemaProcessor, "parse")

    def test_capability_registry_methods(self):
        assert hasattr(CapabilityRegistry, "snapshot")
        assert hasattr(CapabilityRegistry, "resolve")

    def test_assessment_profile_registry_methods(self):
        assert hasattr(AssessmentProfileRegistry, "resolve")
        assert hasattr(AssessmentProfileRegistry, "resolve_compatible")
        assert hasattr(AssessmentProfileRegistry, "publish")

    def test_collector_methods(self):
        assert hasattr(Collector, "collect")

    def test_evidence_store_methods(self):
        assert hasattr(EvidenceStore, "store")
        assert hasattr(EvidenceStore, "retrieve")
        assert hasattr(EvidenceStore, "verify_integrity")

    def test_history_store_methods(self):
        assert hasattr(HistoryStore, "commit")
        assert hasattr(HistoryStore, "query")
        assert hasattr(HistoryStore, "get_result")

    def test_session_factory_methods(self):
        assert hasattr(SessionFactory, "for_account")

    def test_guarded_session_methods(self):
        assert hasattr(GuardedSession, "call")

    def test_telemetry_service_methods(self):
        assert hasattr(TelemetryService, "emit")
        assert hasattr(TelemetryService, "query_by_correlation")


# ---------------------------------------------------------------------------
# Internal exceptions are NOT part of public contract
# ---------------------------------------------------------------------------


class TestNoInternalExceptions:
    """Verify the agentic package does not export exception classes."""

    def test_no_exception_exports(self):
        import agentic
        for name in agentic.__all__:
            obj = getattr(agentic, name)
            if isinstance(obj, type):
                # Should not be an Exception subclass
                assert not issubclass(obj, BaseException), (
                    f"{name} is an exception class — internal exceptions "
                    "must not be part of the public contract"
                )
