"""
Regression test: LegacyInteractiveAdapter vs direct agent invocation
(Task 8.3).

One mocked boto3 session backs BOTH code paths for `s3.inventory`
(a non-EC2 capability):

- Path A ("legacy"): `run_legacy_capability("s3", ...)` — the
  `LegacyInteractiveAdapter` (Task 8.2) — mutates
  `assessment_data['services']['s3']`.
- Path B ("agent"): `invoke()` validates the identical request through the
  same Capability Registry (Req 13.2), then the SAME registered
  `s3.inventory` Collector's `.collect()` is resolved and called directly
  with the SAME target/parameters — `invoke()`'s own `InvocationResult`
  only carries `record_count` per unit (Task 1-5 models are frozen), not
  field-level records, so record-level comparison must go through the
  Collector `invoke()` itself would have selected (see
  `agentic/legacy_adapter.py` module docstring).

Assertion: the underlying bucket records collected by both paths are
identical (Req 13.3) — the adapter's projection does not lose or corrupt
data relative to direct agent invocation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

from botocore.exceptions import ClientError

from agentic.legacy_adapter import run_legacy_capability
from agentic.legacy_contracts import register_all_legacy_capabilities
from agentic.models import AccountTarget, CapabilityRequest, ExecutionContext, InvocationRequest
from agentic.orchestrator import invoke
from agentic.registry import CapabilityRegistryImpl
from agentic.schemas.processor import CanonicalSchemaProcessor
from agentic.session import GuardedSessionImpl, SessionIdentity


def _client_error(code: str) -> ClientError:
    return ClientError(
        error_response={"Error": {"Code": code, "Message": "boom"}},
        operation_name="DescribeSomething",
    )


class _FakeBotoSession:
    """Minimal boto3.session.Session stand-in: `.client()` always returns the
    same scripted mock client, matching `GuardedSessionImpl.call()`'s
    `self._session.client(service, config=...)` usage."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def client(self, service_name: str, config: Any = None) -> Any:
        return self._client


def _make_s3_client() -> MagicMock:
    """One shared mocked S3 client with two buckets, used by both paths."""
    client = MagicMock()
    client.list_buckets.return_value = {
        "Buckets": [
            {"Name": "bucket-a", "CreationDate": datetime(2024, 1, 1, tzinfo=timezone.utc)},
            {"Name": "bucket-b", "CreationDate": datetime(2024, 2, 1, tzinfo=timezone.utc)},
        ]
    }

    def _lifecycle(Bucket: str) -> dict[str, Any]:
        if Bucket == "bucket-a":
            raise _client_error("NoSuchLifecycleConfiguration")
        return {"Rules": [{"ID": "expire-old"}]}

    def _versioning(Bucket: str) -> dict[str, Any]:
        return {"Status": "Enabled"} if Bucket == "bucket-b" else {}

    def _encryption(Bucket: str) -> dict[str, Any]:
        if Bucket == "bucket-a":
            raise _client_error("ServerSideEncryptionConfigurationNotFoundError")
        return {}

    client.get_bucket_lifecycle_configuration.side_effect = _lifecycle
    client.get_bucket_versioning.side_effect = _versioning
    client.get_bucket_encryption.side_effect = _encryption
    return client


def test_legacy_adapter_matches_direct_agent_invocation_for_s3() -> None:
    account_id = "111111111111"
    region = "us-east-1"
    shared_client = _make_s3_client()
    session = _FakeBotoSession(shared_client)

    # --- Path A: legacy wizard route, through LegacyInteractiveAdapter ---
    assessment_data: dict[str, Any] = {"services": {}}
    run_legacy_capability("s3", session, account_id, region, assessment_data)
    legacy_result = assessment_data["services"]["s3"]

    # --- Path B: direct agent route, same registry/target/parameters ---
    registry = CapabilityRegistryImpl()
    register_all_legacy_capabilities(registry)

    request = InvocationRequest(
        capabilities=(CapabilityRequest(id="s3.inventory", version="1.0.0"),),
        targets=(AccountTarget(account_id=account_id),),
        regions=(region,),
        execution_context=ExecutionContext(
            caller_id="regression-test",
            correlation_id="11111111-1111-1111-1111-111111111111",
            purpose="regression-test",
        ),
    )
    validation = invoke(request, registry, CanonicalSchemaProcessor())
    assert validation.execution_status != "failed"

    resolved = registry.resolve("s3.inventory", "1.0.0")
    guarded_session = GuardedSessionImpl(
        session=session,
        allowed_operations=set(resolved.descriptor.allowed_operations),
        identity=SessionIdentity(account_id=account_id),
    )
    outcome = resolved.handler.collect(
        "s3.inventory", "1.0.0", account_id, "aws-global", {}, guarded_session
    )
    assert outcome.status == "succeeded"
    agent_buckets = [dict(r.fields) for r in outcome.records]

    # --- Regression assertion: legacy (via adapter) == agent (via invoke()
    # validation + direct Collector resolution) at the record level ---
    assert legacy_result["buckets"] == agent_buckets
    assert legacy_result["count"] == len(agent_buckets)
    assert {b["name"] for b in legacy_result["buckets"]} == {"bucket-a", "bucket-b"}
