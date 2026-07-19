"""
Legacy Interactive Adapter (Task 8.2).

One small function that lets the interactive wizard (`aws_assessment.py`)
keep selecting a service by its existing code ("s3", "ec2", ...), but route
that selection through the same Capability Registry and `invoke()` contract
path an Agent invocation uses, instead of importing collector functions ad
hoc (Req 13.2).

For service codes that ARE migrated (registered in the Capability Registry,
Task 6.1/6.2): resolves the capability, wraps the wizard's existing boto3
session in a `GuardedSessionImpl` scoped to that capability's read-only
allowlist, runs the registered Collector's `.collect()`, and projects the
returned `CollectorOutcome.records` back into the exact
`assessment_data['services'][service_code]` shape the legacy HTML/PDF
reporter (`core/reporter/*`) already consumes (Req 13.3) — no reporter
change needed.

For service codes that are NOT migrated yet (`lambda`, `eks`, `alb`, `ecr` —
`collectors/compute.py` was never ported to the agentic registry): falls
back to calling the existing legacy collector function directly with the
raw session, exactly as `aws_assessment.py` did before this task. This
preserves current behavior for capabilities Task 6 did not touch.

`invoke()` (agentic/orchestrator.py) is called first to validate the request
through the identical contract path an Agent invocation would use; a
validation failure short-circuits before any AWS call (Req 2.2). `invoke()`
itself only plans — its `unit_results` carry record counts, not the
collected field data, since the Task 1-5 models/orchestrator are frozen —
so the actual record collection below goes through the SAME registered
Collector `invoke()` would have selected for this capability, via
`registry.resolve()` on the SAME `CapabilityRegistryImpl` instance `invoke()`
was given.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable

from agentic.ec2_collector import EC2InventoryCollector
from agentic.ec2_contract import register_ec2_inventory
from agentic.legacy_contracts import register_all_legacy_capabilities
from agentic.models import (
    AccountTarget,
    CapabilityRequest,
    ExecutionContext,
    InvocationRequest,
)
from agentic.orchestrator import invoke
from agentic.registry import CapabilityRegistryImpl, RegisteredCapability
from agentic.schemas.processor import CanonicalSchemaProcessor
from agentic.session import GuardedSessionImpl, SessionIdentity

# ---------------------------------------------------------------------------
# service_code -> capability_id (only migrated services appear here)
# ---------------------------------------------------------------------------
#
# Wizard service codes (aws_assessment.py's `inventory_map` keys) not listed
# here — "lambda", "eks", "alb", "ecr" — have no migrated capability
# (collectors/compute.py's lambda/eks/alb/ecr collectors were not ported in
# Task 6) and always fall back to `legacy_collector`.

SERVICE_TO_CAPABILITY: dict[str, str] = {
    "ec2": "ec2.inventory",
    "s3": "s3.inventory",
    "rds": "rds.inventory",
    "dynamodb": "dynamodb.inventory",
    "cloudfront": "cloudfront.inventory",
    "ebs": "ebs.inventory",
    "elasticache": "elasticache.inventory",
    "vpc": "vpc.inventory",
    "nat_gateway": "nat.inventory",
    "iam": "iam.inventory",
    "kms": "kms.inventory",
    "waf": "waf.inventory",
    "cloudwatch": "cloudwatch.inventory",
    "cloudtrail": "cloudtrail.inventory",
    "config": "config.inventory",
    "efs": "efs.inventory",
    "backup": "backup.inventory",
    "secretsmanager": "secretsmanager.inventory",
    "sns": "sns.inventory",
    "msk": "msk.inventory",
    "amazonmq": "amazonmq.inventory",
    "glue": "glue.inventory",
    "route53": "route53.inventory",
    "nlb": "nlb.inventory",
}

# capability_id -> single list key for the legacy
# assessment_data['services'][code][key] shape (Req 13.3).
_SINGLE_LIST_KEY: dict[str, str] = {
    "s3.inventory": "buckets",
    "ebs.inventory": "volumes",
    "efs.inventory": "file_systems",
    "vpc.inventory": "vpcs",
    "nat.inventory": "nat_gateways",
    "cloudfront.inventory": "distributions",
    "route53.inventory": "hosted_zones",
    "nlb.inventory": "load_balancers",
    "rds.inventory": "instances",
    "dynamodb.inventory": "tables",
    "elasticache.inventory": "clusters",
    "sns.inventory": "topics",
    "msk.inventory": "clusters",
    "amazonmq.inventory": "brokers",
    "cloudwatch.inventory": "alarms",
    "cloudtrail.inventory": "trails",
    "config.inventory": "recorders",
    "kms.inventory": "keys",
    "waf.inventory": "web_acls",
    "secretsmanager.inventory": "secrets",
}

# One ResourceRecord wrapping the whole legacy flat dict (e.g. iam.inventory).
_FLAT_SUMMARY_CAPABILITIES = frozenset({"iam.inventory"})

# Records tagged with `record_type` (singular) by agentic/legacy_collectors.py
# (`_to_resource_records`); regroup by `record_type + "s"` to rebuild the
# legacy {"vaults": [...], "plans": [...]} / {"databases": [...], "jobs": [...]}
# shape.
_MULTI_LIST_CAPABILITIES = frozenset({"backup.inventory", "glue.inventory"})


_registry: CapabilityRegistryImpl | None = None


def _get_registry() -> CapabilityRegistryImpl:
    """Build (once) the same Capability Registry an Agent invocation uses."""
    global _registry
    if _registry is None:
        registry = CapabilityRegistryImpl()
        register_ec2_inventory(registry, EC2InventoryCollector())
        register_all_legacy_capabilities(registry)
        _registry = registry
    return _registry


def _project_ec2_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """ec2.inventory field names differ slightly from the legacy shape."""
    projected = dict(fields)
    projected["id"] = projected.pop("instance_id", "")
    projected["type"] = projected.pop("instance_type", "")
    return projected


def _project_records(capability_id: str, records: tuple[Any, ...]) -> dict[str, Any]:
    """
    Rebuild the exact legacy `assessment_data['services'][code]` shape
    (Req 13.3) from a Collector's `CollectorOutcome.records`.
    """
    if capability_id in _FLAT_SUMMARY_CAPABILITIES:
        fields = dict(records[0].fields) if records else {}
        fields.setdefault("count", fields.get("users_count", 0))
        return fields

    if capability_id in _MULTI_LIST_CAPABILITIES:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for record in records:
            fields = dict(record.fields)
            record_type = fields.pop("record_type", "item")
            grouped.setdefault(f"{record_type}s", []).append(fields)
        result: dict[str, Any] = {"count": sum(len(v) for v in grouped.values())}
        result.update(grouped)
        return result

    if capability_id == "ec2.inventory":
        items = [_project_ec2_fields(dict(r.fields)) for r in records]
        return {"count": len(items), "instances": items}

    list_key = _SINGLE_LIST_KEY[capability_id]
    items = [dict(r.fields) for r in records]
    return {"count": len(items), list_key: items}


def run_legacy_capability(
    service_code: str,
    session: Any,
    account_id: str,
    region: str,
    assessment_data: dict[str, Any],
    legacy_collector: Callable[[Any, dict[str, Any]], Any] | None = None,
) -> None:
    """
    Collect one wizard-selected service, routed through the Capability
    Registry when migrated, falling back to the legacy collector otherwise.

    Mutates `assessment_data['services'][service_code]` in place, matching
    the shape `core/reporter/*` already consumes (Req 13.2, 13.3).

    Args:
        service_code: wizard service code, e.g. "s3", "ec2".
        session: the wizard's existing boto3.Session (already authenticated).
        account_id: resolved AWS account ID (from validate_credentials()).
        region: the wizard's configured AWS region.
        assessment_data: the shared dict mutated in place (legacy shape).
        legacy_collector: fallback `collect(session, assessment_data)`
            function for service codes with no migrated capability. Required
            when `service_code` is not in `SERVICE_TO_CAPABILITY`.
    """
    capability_id = SERVICE_TO_CAPABILITY.get(service_code)

    if capability_id is None:
        # Not migrated (lambda, eks, alb, ecr, ...) — preserve existing
        # behavior exactly.
        if legacy_collector is None:
            raise ValueError(
                f"No registered capability for '{service_code}' and no "
                f"legacy_collector fallback was provided."
            )
        legacy_collector(session, assessment_data)
        return

    registry = _get_registry()

    resolved = registry.resolve(capability_id, "1.0.0")
    if not isinstance(resolved, RegisteredCapability):
        print(f"✗ Error: capability '{capability_id}' is not registered.")
        return

    region_scope = "aws-global" if resolved.descriptor.scope == "global" else region

    request = InvocationRequest(
        capabilities=(CapabilityRequest(id=capability_id, version="1.0.0"),),
        targets=(AccountTarget(account_id=account_id),),
        regions=(region,),
        execution_context=ExecutionContext(
            caller_id="legacy-wizard",
            correlation_id=str(uuid.uuid4()),
            purpose="legacy-interactive",
        ),
    )
    validation = invoke(request, registry, CanonicalSchemaProcessor())
    if validation.execution_status == "failed":
        print(f"✗ Error: invocation validation failed for '{capability_id}'.")
        return

    guarded_session = GuardedSessionImpl(
        session=session,
        allowed_operations=set(resolved.descriptor.allowed_operations),
        identity=SessionIdentity(account_id=account_id),
    )

    outcome = resolved.handler.collect(
        capability_id, "1.0.0", account_id, region_scope, {}, guarded_session
    )

    if outcome.status == "failed":
        safe_message = outcome.error.safe_message if outcome.error else "unknown error"
        print(f"✗ Error inventorying {service_code}: {safe_message}")
        return

    assessment_data["services"][service_code] = _project_records(
        capability_id, outcome.records
    )


if __name__ == "__main__":
    # ponytail: minimal runnable self-check; full coverage in
    # tests/test_legacy_adapter.py.
    from unittest.mock import MagicMock

    from agentic.models import ResourceRecord

    # --- migrated path: s3.inventory projects into the legacy shape ---
    fake_records = (
        ResourceRecord(
            resource_identity="1/aws-global/s3.inventory/bucket-a",
            account_id="111111111111",
            region_scope="aws-global",
            capability_id="s3.inventory",
            fields={
                "name": "bucket-a",
                "creation_date": "2024-01-01 00:00:00",
                "has_lifecycle": False,
                "versioning_status": "Never",
                "encrypted": False,
            },
        ),
    )
    projected = _project_records("s3.inventory", fake_records)
    assert projected["count"] == 1
    assert projected["buckets"][0]["name"] == "bucket-a"

    # --- multi-list path: backup.inventory regroups by record_type ---
    backup_records = (
        ResourceRecord(fields={"name": "vault-a", "record_type": "vault"}),
        ResourceRecord(fields={"name": "plan-a", "record_type": "plan"}),
    )
    backup_projected = _project_records("backup.inventory", backup_records)
    assert backup_projected["count"] == 2
    assert backup_projected["vaults"][0]["name"] == "vault-a"
    assert backup_projected["plans"][0]["name"] == "plan-a"

    # --- flat-summary path: iam.inventory ---
    iam_records = (
        ResourceRecord(fields={"users_count": 3, "groups_count": 1}),
    )
    iam_projected = _project_records("iam.inventory", iam_records)
    assert iam_projected["count"] == 3

    # --- unmigrated fallback path ---
    fallback_called: dict[str, Any] = {}

    def _fake_legacy_collector(session: Any, data: dict[str, Any]) -> bool:
        fallback_called["called"] = True
        data["services"]["lambda"] = {"count": 0, "functions": []}
        return True

    data: dict[str, Any] = {"services": {}}
    run_legacy_capability(
        "lambda", MagicMock(), "111111111111", "us-east-1", data,
        legacy_collector=_fake_legacy_collector,
    )
    assert fallback_called.get("called") is True
    assert data["services"]["lambda"]["count"] == 0

    print("legacy_adapter self-check passed")
