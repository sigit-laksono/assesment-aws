"""
Minimal unit tests for migrated legacy collect() functions (Task 6.2).

Scope: verify each collect_* function dispatches exclusively through
`session.call(service, operation, **kwargs)` (never `session.client(...)`)
and returns plain records without a shared `assessment_data` dict. Full
CollectorOutcome/error-classification coverage is Task 6.3/6.5's job — this
file intentionally stays lightweight per Task 6.2 scope.

Operation names use the same PascalCase convention as
`agentic/legacy_contracts.py`'s `allowed_operations` (Task 6.1) and
`tests/test_session_factory.py`'s `guarded.call("ec2", "DescribeInstances")`
calls (Task 5) — see module docstring in `agentic/legacy_collectors.py` for
the casing-convention rationale.
"""

from __future__ import annotations

from typing import Any

import pytest

from agentic.legacy_collectors import (
    build_legacy_collector,
    collect_backup_inventory,
    collect_cost_optimization_findings,
    collect_ebs_inventory,
    collect_s3_inventory,
    collect_vpc_inventory,
)
from agentic.legacy_contracts import LEGACY_CAPABILITY_SPECS
from agentic.models import StructuredError
from agentic.session import GuardViolationError


class FakeGuardedSession:
    """
    Minimal stand-in for GuardedSessionImpl: routes calls through a
    scripted response table and enforces an allowlist, exactly like the
    real GuardedSession's fail-closed behavior — without touching boto3.
    """

    def __init__(self, responses: dict[str, Any], allowed_operations: set[str]) -> None:
        self._responses = responses
        self._allowed = allowed_operations
        self.calls: list[str] = []

    def call(self, service: str, operation: str, **kwargs: Any) -> Any:
        key = f"{service}:{operation}"
        self.calls.append(key)
        if key not in self._allowed:
            raise GuardViolationError(
                StructuredError(
                    code="GUARD_VIOLATION",
                    category="guard-violation",
                    retryable=False,
                    safe_message=f"Operation '{key}' not in allowlist.",
                )
            )
        if key not in self._responses:
            raise KeyError(f"No scripted response for {key}")
        return self._responses[key]


def _spec_ops(capability_id: str) -> set[str]:
    spec = next(s for s in LEGACY_CAPABILITY_SPECS if s.capability_id == capability_id)
    return set(spec.allowed_operations)


class TestNoDirectBoto3Client:
    """Collectors must never call session.client(...) — only session.call(...)."""

    def test_s3_inventory_uses_only_call(self) -> None:
        session = FakeGuardedSession(
            responses={
                "s3:ListBuckets": {"Buckets": []},
            },
            allowed_operations=_spec_ops("s3.inventory"),
        )
        assert not hasattr(session, "client")
        result = collect_s3_inventory(session)
        assert result == []
        assert session.calls == ["s3:ListBuckets"]

    def test_ebs_inventory_paginates_via_call(self) -> None:
        session = FakeGuardedSession(
            responses={
                "ec2:DescribeVolumes": {
                    "Volumes": [
                        {
                            "VolumeId": "vol-1",
                            "Size": 8,
                            "VolumeType": "gp3",
                            "State": "available",
                            "Encrypted": False,
                        }
                    ]
                },
            },
            allowed_operations=_spec_ops("ebs.inventory"),
        )
        result = collect_ebs_inventory(session)
        assert len(result) == 1
        assert result[0]["id"] == "vol-1"
        assert result[0]["attached_instance"] is None
        assert session.calls == ["ec2:DescribeVolumes"]

    def test_vpc_inventory_returns_records_not_bool(self) -> None:
        session = FakeGuardedSession(
            responses={
                "ec2:DescribeVpcs": {
                    "Vpcs": [
                        {"VpcId": "vpc-1", "CidrBlock": "10.0.0.0/16", "State": "available"}
                    ]
                },
            },
            allowed_operations=_spec_ops("vpc.inventory"),
        )
        result = collect_vpc_inventory(session)
        assert isinstance(result, list)
        assert result[0]["id"] == "vpc-1"

    def test_backup_inventory_multi_call(self) -> None:
        session = FakeGuardedSession(
            responses={
                "backup:ListBackupVaults": {"BackupVaultList": []},
                "backup:ListBackupPlans": {"BackupPlansList": []},
            },
            allowed_operations=_spec_ops("backup.inventory"),
        )
        result = collect_backup_inventory(session)
        assert result == {"vaults": [], "plans": []}
        assert set(session.calls) == {"backup:ListBackupVaults", "backup:ListBackupPlans"}


class TestGuardViolationPropagates:
    """An operation outside the allowlist must fail closed before any response is used."""

    def test_operation_outside_allowlist_raises(self) -> None:
        # Deliberately omit s3:ListBuckets from the allowlist.
        session = FakeGuardedSession(responses={}, allowed_operations=set())
        with pytest.raises(GuardViolationError):
            collect_s3_inventory(session)
        assert session.calls == ["s3:ListBuckets"]


class TestCostOptimizationDerivedShape:
    """cost-optimization.findings takes sibling records as explicit params, not a shared dict."""

    def test_accepts_explicit_records_no_shared_dict(self) -> None:
        session = FakeGuardedSession(
            responses={
                "ec2:DescribeAddresses": {"Addresses": []},
                "elasticloadbalancing:DescribeTargetGroups": {"TargetGroups": []},
            },
            allowed_operations=_spec_ops("cost-optimization.findings"),
        )
        findings = collect_cost_optimization_findings(
            session,
            region="us-east-1",
            ebs_volumes=[{"id": "vol-1", "size": 8, "type": "gp3", "state": "available", "encrypted": False}],
            ec2_instances=[],
            s3_buckets=[],
            load_balancers=[],
        )
        assert any(f["rule"] == "ebs_unattached" for f in findings)
        # No AWS call needed for the ebs_unattached rule (derived from input records)
        assert "ec2:DescribeAddresses" in session.calls


class TestBuildLegacyCollectorFactory:
    """Every registered legacy capability_id resolves to a working Collector."""

    @pytest.mark.parametrize(
        "capability_id",
        [spec.capability_id for spec in LEGACY_CAPABILITY_SPECS],
    )
    def test_factory_returns_collector_with_collect_method(self, capability_id: str) -> None:
        collector = build_legacy_collector(capability_id)
        assert callable(collector.collect)

    def test_unknown_capability_id_raises(self) -> None:
        with pytest.raises(ValueError):
            build_legacy_collector("does-not-exist")
