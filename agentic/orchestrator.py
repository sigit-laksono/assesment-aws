"""
Assessment Orchestrator — Public invoke() and Deterministic Planner.

Implements:
- Public invoke() entry point for agents/adapters (Req 2.1, 2.2)
- Deterministic planner with prerequisite closure (Req 2.3, 2.4)
- Structured error responses for unsupported/invalid requests (Req 2.5)
- EC2 routing isolation (Req 4.6)

Planning excludes timestamps, random UUIDs, network response order,
and process-global state. Runtime identifiers and timestamps are added
only after the plan digest exists.
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from dataclasses import dataclass
from typing import Any, Mapping

from agentic.models import (
    AccountTarget,
    CapabilityManifest,
    CapabilityRequest,
    ExecutionContext,
    ExecutionPlan,
    ExecutionUnit,
    InvocationRequest,
    InvocationResult,
    RequiredProfileItem,
    SchemaViolation,
    SemVer,
    StructuredError,
)
from agentic.profile_registry import AssessmentProfileRegistryImpl
from agentic.registry import CapabilityRegistryImpl, RegisteredCapability
from agentic.schemas.processor import CanonicalSchemaProcessor
from agentic.summary import summarize


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def invoke(
    request: InvocationRequest,
    registry: CapabilityRegistryImpl,
    schema_processor: CanonicalSchemaProcessor,
    profile_registry: AssessmentProfileRegistryImpl | None = None,
) -> InvocationResult:
    """
    Public entry point for agents and adapters.

    Validates the InvocationRequest BEFORE planning. If validation fails,
    returns a StructuredError via InvocationResult without calling AWS API,
    creating sessions, or invoking any Collector.

    Supports two mutually exclusive modes:
    - Explicit capability mode: capabilities listed directly in the request
    - Profile mode: capabilities resolved from an immutable assessment profile

    On success, produces a deterministic ExecutionPlan.

    Args:
        request: The versioned InvocationRequest from the agent/adapter.
        registry: The capability registry with registered capabilities.
        schema_processor: Schema processor for computing digests.
        profile_registry: Optional profile registry for profile mode resolution.

    Returns:
        InvocationResult with either a successful plan or structured errors.
    """
    correlation_id = (
        request.execution_context.correlation_id
        if request.execution_context
        else ""
    )

    # --- Step 1: Validate the request (Req 2.1) ---
    validation_error = _validate_request(request)
    if validation_error is not None:
        # Return structured error without AWS API call (Req 2.2)
        return InvocationResult(
            schema_id="invocation-result",
            schema_version="1.0.0",
            execution_status="failed",
            request_digest="",
            plan_digest="",
            unit_results=(),
            capability_summaries=summarize(()),
            manifest_version="",
            correlation_id=correlation_id,
        )

    # --- Step 2: Take immutable registry snapshot ---
    manifest = registry.snapshot()

    # --- Step 3: Determine mode and resolve capabilities ---
    has_profile = request.profile is not None and request.profile != ""

    if has_profile:
        # --- Profile mode (Req 5.2, 5.4) ---
        profile_result = _resolve_profile(
            request, profile_registry, correlation_id, manifest
        )
        if isinstance(profile_result, InvocationResult):
            return profile_result

        # profile_result is a _ResolvedProfile with capabilities and metadata
        resolved_profile = profile_result

        # Resolve extracted capabilities against capability registry (Req 2.5)
        resolution_error = _resolve_capabilities(
            resolved_profile.capabilities, registry
        )
        if resolution_error is not None:
            return InvocationResult(
                schema_id="invocation-result",
                schema_version="1.0.0",
                execution_status="failed",
                request_digest="",
                plan_digest="",
                manifest_version=manifest.manifest_digest,
                unit_results=(),
                capability_summaries=summarize(()),
                correlation_id=correlation_id,
            )

        # Plan with profile metadata
        plan = _plan(
            request,
            manifest,
            registry,
            schema_processor,
            capabilities_override=resolved_profile.capabilities,
            profile_digest=resolved_profile.profile_digest,
            profile_items=resolved_profile.profile_items,
        )

        return InvocationResult(
            schema_id="invocation-result",
            schema_version="1.0.0",
            execution_status="succeeded",
            request_digest=plan.request_digest,
            plan_digest=plan.plan_digest,
            manifest_version=manifest.manifest_digest,
            profile_id=resolved_profile.profile_id,
            profile_version=resolved_profile.profile_version,
            unit_results=(),
            capability_summaries=summarize(()),
            correlation_id=correlation_id,
        )
    else:
        # --- Explicit capability mode ---
        assert request.capabilities is not None  # validated above
        resolution_error = _resolve_capabilities(request.capabilities, registry)
        if resolution_error is not None:
            return InvocationResult(
                schema_id="invocation-result",
                schema_version="1.0.0",
                execution_status="failed",
                request_digest="",
                plan_digest="",
                manifest_version=manifest.manifest_digest,
                unit_results=(),
                capability_summaries=summarize(()),
                correlation_id=correlation_id,
            )

        # --- Step 4: Deterministic planning (Req 2.3, 2.4, 4.6) ---
        plan = _plan(request, manifest, registry, schema_processor)

        return InvocationResult(
            schema_id="invocation-result",
            schema_version="1.0.0",
            execution_status="succeeded",
            request_digest=plan.request_digest,
            plan_digest=plan.plan_digest,
            manifest_version=manifest.manifest_digest,
            unit_results=(),
            capability_summaries=summarize(()),
            correlation_id=correlation_id,
        )


# ---------------------------------------------------------------------------
# Validation (Req 2.1, 2.2)
# ---------------------------------------------------------------------------


def _validate_request(request: InvocationRequest) -> StructuredError | None:
    """
    Validate the InvocationRequest before planning.

    Checks:
    - Exactly one of capabilities or profile must be set
    - At least one target must be declared
    - At least one region must be declared
    - Execution context must be present
    - Capabilities must have valid format

    Returns StructuredError if validation fails, None if valid.
    """
    violations: list[SchemaViolation] = []

    # Check mutually exclusive: exactly one of capabilities or profile
    has_capabilities = request.capabilities is not None and len(request.capabilities) > 0
    has_profile = request.profile is not None and request.profile != ""

    if has_capabilities and has_profile:
        violations.append(
            SchemaViolation(
                json_path="$",
                constraint="mutual_exclusion",
                safe_message=(
                    "Exactly one of 'capabilities' or 'profile' must be set, "
                    "not both."
                ),
            )
        )
    elif not has_capabilities and not has_profile:
        violations.append(
            SchemaViolation(
                json_path="$",
                constraint="required_selection",
                safe_message=(
                    "Exactly one of 'capabilities' or 'profile' must be set."
                ),
            )
        )

    # Check targets
    if not request.targets or len(request.targets) == 0:
        violations.append(
            SchemaViolation(
                json_path="$.targets",
                constraint="minItems",
                safe_message="At least one target account must be declared.",
            )
        )

    # Check regions
    if not request.regions or len(request.regions) == 0:
        violations.append(
            SchemaViolation(
                json_path="$.regions",
                constraint="minItems",
                safe_message="At least one region must be declared.",
            )
        )

    # Check execution context
    if request.execution_context is None:
        violations.append(
            SchemaViolation(
                json_path="$.execution_context",
                constraint="required",
                safe_message="Execution context is required.",
            )
        )
    else:
        # Validate execution context fields
        if not request.execution_context.caller_id:
            violations.append(
                SchemaViolation(
                    json_path="$.execution_context.caller_id",
                    constraint="minLength",
                    safe_message="Caller ID must not be empty.",
                )
            )
        if not request.execution_context.correlation_id:
            violations.append(
                SchemaViolation(
                    json_path="$.execution_context.correlation_id",
                    constraint="minLength",
                    safe_message="Correlation ID must not be empty.",
                )
            )

    # Validate capability entries if present
    if has_capabilities and request.capabilities:
        for idx, cap in enumerate(request.capabilities):
            if not cap.id:
                violations.append(
                    SchemaViolation(
                        json_path=f"$.capabilities[{idx}].id",
                        constraint="minLength",
                        safe_message=f"Capability ID at index {idx} must not be empty.",
                    )
                )
            if not cap.version:
                violations.append(
                    SchemaViolation(
                        json_path=f"$.capabilities[{idx}].version",
                        constraint="minLength",
                        safe_message=(
                            f"Capability version at index {idx} must not be empty."
                        ),
                    )
                )
            else:
                # Validate version format
                try:
                    SemVer.parse(cap.version)
                except ValueError:
                    violations.append(
                        SchemaViolation(
                            json_path=f"$.capabilities[{idx}].version",
                            constraint="format",
                            safe_message=(
                                f"Capability version '{cap.version}' at index {idx} "
                                f"is not valid semver (expected 'major.minor.patch')."
                            ),
                        )
                    )

    if violations:
        return StructuredError(
            schema_id="structured-error",
            schema_version="1.0.0",
            code="VALIDATION_ERROR",
            category="validation",
            retryable=False,
            safe_message="Invocation request validation failed.",
            violations=tuple(violations),
        )

    return None


def _resolve_capabilities(
    capabilities: tuple[CapabilityRequest, ...],
    registry: CapabilityRegistryImpl,
) -> StructuredError | None:
    """
    Resolve all requested capabilities from the registry.
    Returns StructuredError if any capability is unsupported (Req 2.5).
    """
    for cap in capabilities:
        result = registry.resolve(cap.id, cap.version)
        if isinstance(result, StructuredError):
            return result
    return None


# ---------------------------------------------------------------------------
# Profile Resolution (Req 5.2, 5.4)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ResolvedProfile:
    """Internal result of successful profile resolution."""

    profile_id: str
    profile_version: str
    profile_digest: str
    capabilities: tuple[CapabilityRequest, ...]
    profile_items: tuple[RequiredProfileItem, ...] = ()


def _resolve_profile(
    request: InvocationRequest,
    profile_registry: AssessmentProfileRegistryImpl | None,
    correlation_id: str,
    manifest: CapabilityManifest,
) -> "_ResolvedProfile | InvocationResult":
    """
    Resolve a profile from the profile string in the request.

    Profile string format: "profile_id@version" (e.g., "monthly-standard@1.0.0")

    Returns _ResolvedProfile on success, or InvocationResult (failed) on error.

    Rejection rules:
    - No profile_registry provided: error
    - Profile not found (unsupported version): error
    - Profile status is "retired": error
    - Profile status is "draft" and purpose is "monthly-assessment": error
    - Profile has no items: error
    """
    assert request.profile is not None

    # If no profile registry is provided, profile mode is unavailable
    if profile_registry is None:
        return InvocationResult(
            schema_id="invocation-result",
            schema_version="1.0.0",
            execution_status="failed",
            request_digest="",
            plan_digest="",
            manifest_version=manifest.manifest_digest,
            unit_results=(),
            capability_summaries=summarize(()),
            correlation_id=correlation_id,
        )

    # Parse profile string as "profile_id@version"
    profile_str = request.profile
    if "@" not in profile_str:
        return InvocationResult(
            schema_id="invocation-result",
            schema_version="1.0.0",
            execution_status="failed",
            request_digest="",
            plan_digest="",
            manifest_version=manifest.manifest_digest,
            unit_results=(),
            capability_summaries=summarize(()),
            correlation_id=correlation_id,
        )

    parts = profile_str.split("@", 1)
    profile_id = parts[0]
    version_str = parts[1]

    # Resolve exact version from registry (Req 5.2)
    resolve_result = profile_registry.resolve(profile_id, version_str)

    if isinstance(resolve_result, StructuredError):
        # Profile not found / unsupported version
        return InvocationResult(
            schema_id="invocation-result",
            schema_version="1.0.0",
            execution_status="failed",
            request_digest="",
            plan_digest="",
            manifest_version=manifest.manifest_digest,
            unit_results=(),
            capability_summaries=summarize(()),
            correlation_id=correlation_id,
        )

    profile = resolve_result

    # Reject retired profiles
    if profile.status == "retired":
        return InvocationResult(
            schema_id="invocation-result",
            schema_version="1.0.0",
            execution_status="failed",
            request_digest="",
            plan_digest="",
            manifest_version=manifest.manifest_digest,
            unit_results=(),
            capability_summaries=summarize(()),
            correlation_id=correlation_id,
        )

    # Reject draft profiles for scheduled monthly-assessment runs
    purpose = (
        request.execution_context.purpose if request.execution_context else ""
    )
    if profile.status == "draft" and purpose == "monthly-assessment":
        return InvocationResult(
            schema_id="invocation-result",
            schema_version="1.0.0",
            execution_status="failed",
            request_digest="",
            plan_digest="",
            manifest_version=manifest.manifest_digest,
            unit_results=(),
            capability_summaries=summarize(()),
            correlation_id=correlation_id,
        )

    # Reject profiles with no items
    if not profile.items or len(profile.items) == 0:
        return InvocationResult(
            schema_id="invocation-result",
            schema_version="1.0.0",
            execution_status="failed",
            request_digest="",
            plan_digest="",
            manifest_version=manifest.manifest_digest,
            unit_results=(),
            capability_summaries=summarize(()),
            correlation_id=correlation_id,
        )

    # Extract capabilities from profile items
    capabilities = tuple(
        CapabilityRequest(
            id=item.capability_id,
            version=item.capability_version,
            parameters={},
        )
        for item in profile.items
    )

    # Compute profile digest
    profile_digest = profile_registry._compute_content_digest(profile)

    return _ResolvedProfile(
        profile_id=profile_id,
        profile_version=version_str,
        profile_digest=profile_digest,
        capabilities=capabilities,
        profile_items=profile.items,
    )


# ---------------------------------------------------------------------------
# Deterministic Planner (Req 2.3, 2.4, 4.6)
# ---------------------------------------------------------------------------


def _plan(
    request: InvocationRequest,
    manifest: CapabilityManifest,
    registry: CapabilityRegistryImpl,
    schema_processor: CanonicalSchemaProcessor,
    capabilities_override: tuple[CapabilityRequest, ...] | None = None,
    profile_digest: str | None = None,
    profile_items: tuple[RequiredProfileItem, ...] | None = None,
    discovered_regions: Mapping[str, tuple[str, ...]] | None = None,
) -> ExecutionPlan:
    """
    Create a deterministic ExecutionPlan.

    - Resolves prerequisite closure with topological sort (capability_id tie-breaker)
    - Normalizes and sorts targets (account, region)
    - Creates ExecutionUnits for each capability-target pair
    - Global capabilities use scope 'aws-global' once per account
    - Regional capabilities expand to every (account, region) pair
    - Generates stable unit IDs from (request_digest, capability_version,
      account, region/global scope, ordinal)
    - Computes plan_digest BEFORE runtime IDs/timestamps
    - Records region_discovery_snapshot when discovered_regions is provided

    Two canonical-equivalent requests with same registry produce
    equivalent ordered ExecutionPlans (Req 2.3).

    Args:
        request: The invocation request.
        manifest: Immutable capability manifest snapshot.
        registry: The capability registry.
        schema_processor: For digest computation.
        capabilities_override: If set, use these capabilities instead of
            request.capabilities (used in profile mode).
        profile_digest: If set, include in the execution plan.
        profile_items: If set, use target_scope from profile items to
            determine capability scope (overrides descriptor scope).
        discovered_regions: If set, maps account_id -> sorted discovered
            region codes. Used for region discovery mode.
    """
    capabilities = capabilities_override or request.capabilities
    assert capabilities is not None

    # --- Step 1: Compute request digest ---
    request_digest = _compute_request_digest(request, schema_processor)

    # --- Step 2: Resolve prerequisite closure (topological sort) ---
    ordered_capabilities = _resolve_prerequisite_closure(
        capabilities, registry
    )

    # --- Step 3: Build scope map for each capability ---
    # Priority: profile_items > descriptor.scope
    scope_map = _build_scope_map(ordered_capabilities, profile_items)

    # --- Step 4: Normalize targets ---
    # Regional targets: account x region pairs (deduplicated, sorted)
    regional_targets = _normalize_targets(request.targets, request.regions)
    # Global targets: one (account, 'aws-global') per account
    global_targets = _normalize_global_targets(request.targets)

    # --- Step 5: Build region discovery snapshot ---
    region_discovery_snapshot: Mapping[str, tuple[str, ...]] = {}
    if discovered_regions is not None:
        # Sort AND deduplicate: keys sorted, values sorted+deduplicated tuples.
        # Discovery sources (e.g. DescribeRegions) may return shuffled or
        # duplicate entries; the persisted snapshot must be a stable,
        # deduplicated, sorted set (Req 6.2).
        region_discovery_snapshot = {
            k: tuple(sorted(set(v)))
            for k, v in sorted(discovered_regions.items())
        }

    # --- Step 6: Create ExecutionUnits ---
    units: list[ExecutionUnit] = []
    ordinal = 0

    for cap_entry in ordered_capabilities:
        descriptor = cap_entry.descriptor
        cap_scope = scope_map.get(descriptor.capability_id, "regional")

        # Find original parameters (empty for prerequisites not in original request)
        params = _get_parameters_for_capability(
            descriptor.capability_id, str(descriptor.version), capabilities
        )

        if cap_scope == "global":
            # Global capabilities: one unit per account with 'aws-global' scope
            for account_id, region_scope in global_targets:
                unit_id = _compute_unit_id(
                    request_digest=request_digest,
                    capability_version=str(descriptor.version),
                    account_id=account_id,
                    region_scope=region_scope,
                    ordinal=ordinal,
                )

                # Find prerequisite unit IDs
                prereq_unit_ids = _find_prerequisite_unit_ids(
                    descriptor.prerequisites, account_id, region_scope, units
                )

                unit = ExecutionUnit(
                    unit_id=unit_id,
                    ordinal=ordinal,
                    capability_id=descriptor.capability_id,
                    capability_version=str(descriptor.version),
                    account_id=account_id,
                    region_scope=region_scope,
                    parameters=dict(params),
                    prerequisite_unit_ids=tuple(prereq_unit_ids),
                )
                units.append(unit)
                ordinal += 1
        else:
            # Regional (or derived) capabilities: one unit per (account, region) pair
            for account_id, region_scope in regional_targets:
                unit_id = _compute_unit_id(
                    request_digest=request_digest,
                    capability_version=str(descriptor.version),
                    account_id=account_id,
                    region_scope=region_scope,
                    ordinal=ordinal,
                )

                # Find prerequisite unit IDs — look for same target OR global prereq
                prereq_unit_ids = _find_prerequisite_unit_ids(
                    descriptor.prerequisites, account_id, region_scope, units
                )

                unit = ExecutionUnit(
                    unit_id=unit_id,
                    ordinal=ordinal,
                    capability_id=descriptor.capability_id,
                    capability_version=str(descriptor.version),
                    account_id=account_id,
                    region_scope=region_scope,
                    parameters=dict(params),
                    prerequisite_unit_ids=tuple(prereq_unit_ids),
                )
                units.append(unit)
                ordinal += 1

    # --- Step 7: Compute plan digest BEFORE runtime IDs/timestamps ---
    plan_digest = _compute_plan_digest(
        request_digest=request_digest,
        manifest_digest=manifest.manifest_digest,
        units=tuple(units),
    )

    return ExecutionPlan(
        schema_id="execution-plan",
        schema_version="1.0.0",
        request_digest=request_digest,
        manifest_digest=manifest.manifest_digest,
        profile_digest=profile_digest,
        region_discovery_snapshot=region_discovery_snapshot,
        units=tuple(units),
        plan_digest=plan_digest,
    )


# ---------------------------------------------------------------------------
# Prerequisite Closure (Req 2.4)
# ---------------------------------------------------------------------------


def _resolve_prerequisite_closure(
    requested_capabilities: tuple[CapabilityRequest, ...],
    registry: CapabilityRegistryImpl,
) -> list[RegisteredCapability]:
    """
    Form the prerequisite closure for the requested capabilities.

    Uses BFS to discover all transitive prerequisites, then performs a
    topological sort with capability_id as tie-breaker to ensure
    deterministic ordering.

    Only the requested capability and its declared prerequisites are
    included — no unrelated capabilities (Req 2.4, 4.6).
    """
    # Collect all capabilities needed (requested + transitive prerequisites)
    needed: dict[str, RegisteredCapability] = {}

    # BFS to discover all transitive prerequisites
    queue: deque[str] = deque()

    for cap_req in requested_capabilities:
        result = registry.resolve(cap_req.id, cap_req.version)
        if isinstance(result, RegisteredCapability):
            needed[cap_req.id] = result
            queue.append(cap_req.id)

    while queue:
        current_id = queue.popleft()
        entry = needed[current_id]
        for prereq_id in entry.descriptor.prerequisites:
            if prereq_id not in needed:
                # Resolve prerequisite using major-compatible resolution
                prereq_result = registry.resolve_compatible(
                    prereq_id,
                    # Use the highest available major version
                    _get_latest_major(prereq_id, registry),
                )
                if isinstance(prereq_result, RegisteredCapability):
                    needed[prereq_id] = prereq_result
                    queue.append(prereq_id)

    # Topological sort with capability_id as tie-breaker
    return _topological_sort(needed)


def _get_latest_major(capability_id: str, registry: CapabilityRegistryImpl) -> int:
    """Get the latest major version for a capability in the registry."""
    entries = registry._entries.get(capability_id, {})
    if not entries:
        return 1
    return max(entries.keys())


def _topological_sort(
    capabilities: dict[str, RegisteredCapability],
) -> list[RegisteredCapability]:
    """
    Perform topological sort on capabilities based on their prerequisites.
    Uses capability_id as tie-breaker for deterministic ordering.
    """
    # Build in-degree map (only counting edges within our set)
    in_degree: dict[str, int] = {cap_id: 0 for cap_id in capabilities}
    for cap_id, entry in capabilities.items():
        for prereq_id in entry.descriptor.prerequisites:
            if prereq_id in capabilities:
                in_degree[cap_id] = in_degree.get(cap_id, 0) + 1

    # Kahn's algorithm with sorted frontier (capability_id as tie-breaker)
    ready: list[str] = sorted(
        [cap_id for cap_id, degree in in_degree.items() if degree == 0]
    )
    result: list[RegisteredCapability] = []

    while ready:
        # Take the first (lexicographically smallest) ready capability
        current = ready.pop(0)
        result.append(capabilities[current])

        # Reduce in-degree for dependents
        for cap_id, entry in capabilities.items():
            if current in entry.descriptor.prerequisites:
                in_degree[cap_id] -= 1
                if in_degree[cap_id] == 0:
                    # Insert in sorted position
                    ready.append(cap_id)
                    ready.sort()

    return result


# ---------------------------------------------------------------------------
# Target Normalization
# ---------------------------------------------------------------------------


def _normalize_targets(
    accounts: tuple[AccountTarget, ...],
    regions: tuple[str, ...],
) -> list[tuple[str, str]]:
    """
    Normalize and deduplicate targets, then sort lexicographically.
    Returns list of (account_id, region_scope) pairs for regional scope.
    """
    targets: set[tuple[str, str]] = set()
    for account in accounts:
        for region in regions:
            targets.add((account.account_id, region))
    return sorted(targets)


def _normalize_global_targets(
    accounts: tuple[AccountTarget, ...],
) -> list[tuple[str, str]]:
    """
    Normalize global targets: one (account_id, 'aws-global') per account.
    Deduplicated and sorted lexicographically.
    """
    targets: set[tuple[str, str]] = set()
    for account in accounts:
        targets.add((account.account_id, "aws-global"))
    return sorted(targets)


# ---------------------------------------------------------------------------
# Digest Computation
# ---------------------------------------------------------------------------


def _compute_request_digest(
    request: InvocationRequest,
    schema_processor: CanonicalSchemaProcessor,
) -> str:
    """
    Compute a deterministic digest of the request's canonical content.
    Excludes runtime fields (timestamps, random IDs).
    """
    # Build canonical representation of the request
    canonical_data: dict[str, Any] = {
        "schema_id": request.schema_id,
        "schema_version": request.schema_version,
    }

    if request.capabilities:
        canonical_data["capabilities"] = [
            {
                "id": cap.id,
                "version": cap.version,
                "parameters": dict(cap.parameters) if cap.parameters else {},
            }
            for cap in request.capabilities
        ]
    else:
        canonical_data["capabilities"] = None

    canonical_data["profile"] = request.profile

    # Normalize targets/regions before hashing: shuffled ordering or
    # duplicate entries in the raw request (e.g. from a region discovery
    # source) must not change the digest, since the planner itself
    # deduplicates and sorts them before building execution units
    # (Req 6.1, 6.2).
    deduped_targets = sorted(
        {(t.account_id, t.role_ref) for t in request.targets}
    )
    canonical_data["targets"] = [
        {"account_id": account_id, "role_ref": role_ref}
        for account_id, role_ref in deduped_targets
    ]

    canonical_data["regions"] = sorted(set(request.regions))

    if request.execution_context:
        canonical_data["execution_context"] = {
            "caller_id": request.execution_context.caller_id,
            "correlation_id": request.execution_context.correlation_id,
            "idempotency_key": request.execution_context.idempotency_key,
            "purpose": request.execution_context.purpose,
            "timeout_seconds": request.execution_context.timeout_seconds,
        }
    else:
        canonical_data["execution_context"] = None

    canonical_bytes = json.dumps(
        canonical_data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    return hashlib.sha256(canonical_bytes).hexdigest()


def _compute_unit_id(
    request_digest: str,
    capability_version: str,
    account_id: str,
    region_scope: str,
    ordinal: int,
) -> str:
    """
    Compute a stable unit ID from deterministic inputs.
    unit_id = SHA-256(request_digest + capability_version + account + region + ordinal)
    """
    content = (
        f"{request_digest}:{capability_version}:{account_id}"
        f":{region_scope}:{ordinal}"
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:32]


def _compute_plan_digest(
    request_digest: str,
    manifest_digest: str,
    units: tuple[ExecutionUnit, ...],
) -> str:
    """
    Compute plan digest over the plan's deterministic content.
    This is computed BEFORE runtime IDs/timestamps are added.
    """
    plan_data: dict[str, Any] = {
        "request_digest": request_digest,
        "manifest_digest": manifest_digest,
        "units": [
            {
                "unit_id": u.unit_id,
                "ordinal": u.ordinal,
                "capability_id": u.capability_id,
                "capability_version": u.capability_version,
                "account_id": u.account_id,
                "region_scope": u.region_scope,
                "parameters": dict(u.parameters) if u.parameters else {},
                "prerequisite_unit_ids": list(u.prerequisite_unit_ids),
            }
            for u in units
        ],
    }

    canonical_bytes = json.dumps(
        plan_data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    return hashlib.sha256(canonical_bytes).hexdigest()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_parameters_for_capability(
    capability_id: str,
    capability_version: str,
    requested: tuple[CapabilityRequest, ...],
) -> Mapping[str, Any]:
    """
    Get parameters for a capability from the original request.
    Prerequisites not explicitly requested get empty parameters.
    """
    for cap in requested:
        if cap.id == capability_id and cap.version == capability_version:
            return cap.parameters
    # For prerequisites not in the original request, use empty params
    return {}


def _find_prerequisite_unit_ids(
    prerequisite_cap_ids: tuple[str, ...],
    account_id: str,
    region_scope: str,
    existing_units: list[ExecutionUnit],
) -> list[str]:
    """
    Find unit IDs for prerequisites that match the same target pair.

    For a regional unit, a global prerequisite (scope='aws-global') for the
    same account satisfies the dependency. This ensures global units run
    before any regional unit of that account.
    """
    prereq_ids: list[str] = []
    for prereq_cap_id in prerequisite_cap_ids:
        found = False
        # First try exact match (same account_id and region_scope)
        for unit in existing_units:
            if (
                unit.capability_id == prereq_cap_id
                and unit.account_id == account_id
                and unit.region_scope == region_scope
            ):
                prereq_ids.append(unit.unit_id)
                found = True
                break
        # If not found and this is a regional unit, look for global prereq
        if not found and region_scope != "aws-global":
            for unit in existing_units:
                if (
                    unit.capability_id == prereq_cap_id
                    and unit.account_id == account_id
                    and unit.region_scope == "aws-global"
                ):
                    prereq_ids.append(unit.unit_id)
                    break
    return prereq_ids


def _build_scope_map(
    ordered_capabilities: list[RegisteredCapability],
    profile_items: tuple[RequiredProfileItem, ...] | None = None,
) -> dict[str, str]:
    """
    Build a mapping of capability_id -> scope ('global', 'regional', 'derived').

    Scope determination priority:
    1. Profile items' target_scope (if profile_items provided)
    2. Capability descriptor's scope field

    Returns dict mapping capability_id to its effective scope.
    """
    scope_map: dict[str, str] = {}

    # Build profile-based scope lookup if available
    profile_scope_lookup: dict[str, str] = {}
    if profile_items:
        for item in profile_items:
            profile_scope_lookup[item.capability_id] = item.target_scope

    for cap_entry in ordered_capabilities:
        cap_id = cap_entry.descriptor.capability_id
        # Priority: profile_items > descriptor.scope
        if cap_id in profile_scope_lookup:
            scope_map[cap_id] = profile_scope_lookup[cap_id]
        else:
            scope_map[cap_id] = cap_entry.descriptor.scope

    return scope_map


def _validate_prerequisite_unit_dependencies(
    units: tuple[ExecutionUnit, ...],
) -> list[str]:
    """
    Validate that all prerequisite_unit_ids in the plan reference valid
    unit IDs that exist in the plan.

    Returns a list of error messages (empty if all valid).
    """
    valid_unit_ids = {u.unit_id for u in units}
    errors: list[str] = []
    for unit in units:
        for prereq_id in unit.prerequisite_unit_ids:
            if prereq_id not in valid_unit_ids:
                errors.append(
                    f"Unit '{unit.unit_id}' (capability={unit.capability_id}, "
                    f"ordinal={unit.ordinal}) references non-existent "
                    f"prerequisite unit '{prereq_id}'."
                )
    return errors
