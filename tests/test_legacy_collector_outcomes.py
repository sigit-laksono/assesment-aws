"""
Unit tests for CollectorOutcome wrapping around legacy collect() adapters
(Task 6.3).

Scope: verify `LegacyRecordsCollector.collect()` / `CostOptimizationFindingsCollector.collect()`
return `CollectorOutcome` (never a plain list/dict/bool) and that
`_map_client_error` classifies AWS error codes correctly. Per-capability
exhaustive coverage (all 25 capabilities x success/AccessDenied/allowlist)
is Task 6.5's job — this file covers a representative sample of the
different record shapes plus the deterministic error mapping table.
"""

from __future__ import annotations

from typing import Any

import pytest
from botocore.exceptions import ClientError

from agentic.legacy_collectors import LegacyRecordsCollector, _map_client_error
from agentic.models import CollectorOutcome, StructuredError
from agentic.session import GuardViolationError


class FakeGuardedSession:
    """Minimal GuardedSession stand-in: scripted responses + allowlist enforcement."""

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
        response = self._responses[key]
        if isinstance(response, Exception):
            raise response
        return response


def _client_error(code: str, message: str = "boom") -> ClientError:
    return ClientError(
        error_response={"Error": {"Code": code, "Message": message}},
        operation_name="DescribeSomething",
    )


# ---------------------------------------------------------------------------
# _map_client_error mapping table (Req 8.1, 8.2, 9.1)
# ---------------------------------------------------------------------------


class TestMapClientError:
    @pytest.mark.parametrize("code", ["AccessDenied", "UnauthorizedAccess", "AuthFailure"])
    def test_permission_denied_codes(self, code: str) -> None:
        error = _map_client_error(_client_error(code), "s3.inventory", "111", "us-east-1")
        assert error.category == "permission-denied"
        assert error.retryable is False
        assert error.code == code

    @pytest.mark.parametrize("code", ["Throttling", "RequestLimitExceeded"])
    def test_throttled_codes(self, code: str) -> None:
        error = _map_client_error(_client_error(code), "s3.inventory", "111", "us-east-1")
        assert error.category == "throttled"
        assert error.retryable is True

    def test_other_codes_map_to_internal(self) -> None:
        error = _map_client_error(
            _client_error("SomeOtherError"), "s3.inventory", "111", "us-east-1"
        )
        assert error.category == "internal"
        assert error.retryable is False


# ---------------------------------------------------------------------------
# LegacyRecordsCollector.collect() -> CollectorOutcome
# ---------------------------------------------------------------------------


class TestCollectorOutcomeSuccess:
    def test_list_of_dicts_shape_s3(self) -> None:
        """s3.inventory: collect_s3_inventory returns list[dict] -> one record each."""
        session = FakeGuardedSession(
            responses={
                "s3:ListBuckets": {
                    "Buckets": [{"Name": "bucket-a", "CreationDate": None}]
                },
                "s3:GetBucketLifecycleConfiguration": _client_error("NoSuchLifecycleConfiguration"),
                "s3:GetBucketVersioning": {},
                "s3:GetBucketEncryption": _client_error("ServerSideEncryptionConfigurationNotFoundError"),
            },
            allowed_operations={
                "s3:ListBuckets", "s3:GetBucketLifecycleConfiguration",
                "s3:GetBucketVersioning", "s3:GetBucketEncryption",
            },
        )
        collector = LegacyRecordsCollector("s3.inventory")
        outcome = collector.collect("s3.inventory", "1.0.0", "111", "us-east-1", {}, session)

        assert isinstance(outcome, CollectorOutcome)
        assert outcome.status == "succeeded"
        assert len(outcome.records) == 1
        assert outcome.records[0].fields["name"] == "bucket-a"
        assert len(outcome.evidence) == 1

    def test_empty_result_still_succeeded(self) -> None:
        """collect_s3_inventory returning [] (no buckets) must stay succeeded/records=()."""
        session = FakeGuardedSession(
            responses={"s3:ListBuckets": {"Buckets": []}},
            allowed_operations={"s3:ListBuckets"},
        )
        collector = LegacyRecordsCollector("s3.inventory")
        outcome = collector.collect("s3.inventory", "1.0.0", "111", "us-east-1", {}, session)

        assert outcome.status == "succeeded"
        assert outcome.records == ()

    def test_single_flat_dict_shape_iam(self) -> None:
        """iam.inventory: collect_iam_inventory returns one summary dict -> one record."""
        session = FakeGuardedSession(
            responses={
                "iam:GetAccountSummary": {"SummaryMap": {"Users": 3, "AccountMFAEnabled": 1}},
                "iam:GetAccountPasswordPolicy": _client_error("NoSuchEntity"),
            },
            allowed_operations={"iam:GetAccountSummary", "iam:GetAccountPasswordPolicy"},
        )
        collector = LegacyRecordsCollector("iam.inventory")
        outcome = collector.collect("iam.inventory", "1.0.0", "111", "aws-global", {}, session)

        assert outcome.status == "succeeded"
        assert len(outcome.records) == 1
        assert outcome.records[0].fields["users_count"] == 3

    def test_multi_list_dict_shape_backup(self) -> None:
        """backup.inventory: dict of {vaults, plans} -> one record per item, tagged record_type."""
        session = FakeGuardedSession(
            responses={
                "backup:ListBackupVaults": {
                    "BackupVaultList": [{"BackupVaultName": "vault-1", "BackupVaultArn": "arn:1"}]
                },
                "backup:ListBackupPlans": {
                    "BackupPlansList": [{"BackupPlanId": "plan-1", "BackupPlanName": "plan-1", "VersionId": "v1"}]
                },
            },
            allowed_operations={"backup:ListBackupVaults", "backup:ListBackupPlans"},
        )
        collector = LegacyRecordsCollector("backup.inventory")
        outcome = collector.collect("backup.inventory", "1.0.0", "111", "us-east-1", {}, session)

        assert outcome.status == "succeeded"
        assert len(outcome.records) == 2
        record_types = {r.fields["record_type"] for r in outcome.records}
        assert record_types == {"vault", "plan"}


class TestCollectorOutcomeFailure:
    def test_guard_violation_maps_to_failed(self) -> None:
        session = FakeGuardedSession(responses={}, allowed_operations=set())
        collector = LegacyRecordsCollector("s3.inventory")
        outcome = collector.collect("s3.inventory", "1.0.0", "111", "us-east-1", {}, session)

        assert outcome.status == "failed"
        assert outcome.error is not None
        assert outcome.error.category == "guard-violation"

    def test_access_denied_maps_to_permission_denied(self) -> None:
        session = FakeGuardedSession(
            responses={"s3:ListBuckets": _client_error("AccessDenied")},
            allowed_operations={"s3:ListBuckets"},
        )
        collector = LegacyRecordsCollector("s3.inventory")
        outcome = collector.collect("s3.inventory", "1.0.0", "111", "us-east-1", {}, session)

        assert outcome.status == "failed"
        assert outcome.error is not None
        assert outcome.error.category == "permission-denied"
        assert outcome.error.retryable is False

    def test_throttling_maps_to_throttled_retryable(self) -> None:
        session = FakeGuardedSession(
            responses={"s3:ListBuckets": _client_error("Throttling")},
            allowed_operations={"s3:ListBuckets"},
        )
        collector = LegacyRecordsCollector("s3.inventory")
        outcome = collector.collect("s3.inventory", "1.0.0", "111", "us-east-1", {}, session)

        assert outcome.status == "failed"
        assert outcome.error is not None
        assert outcome.error.category == "throttled"
        assert outcome.error.retryable is True

    def test_other_client_error_maps_to_internal(self) -> None:
        session = FakeGuardedSession(
            responses={"s3:ListBuckets": _client_error("InternalError")},
            allowed_operations={"s3:ListBuckets"},
        )
        collector = LegacyRecordsCollector("s3.inventory")
        outcome = collector.collect("s3.inventory", "1.0.0", "111", "us-east-1", {}, session)

        assert outcome.status == "failed"
        assert outcome.error is not None
        assert outcome.error.category == "internal"
