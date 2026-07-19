"""
Systematic per-capability migration test matrix (Task 6.5).

For EVERY capability_id registered in `agentic/legacy_contracts.py`'s
`LEGACY_CAPABILITY_SPECS` (25 capabilities — one per AWS resource
type/Collector function, per the Task 6.1 scoping decision, not one per
legacy file), this file exercises the same three-test contract:

1. success:  all of the capability's `allowed_operations` are mocked with a
   minimal valid AWS response shape -> `CollectorOutcome.status == "succeeded"`.
2. AccessDenied: the capability's first/primary `allowed_operations` entry
   raises `ClientError(AccessDenied)` -> `status == "failed"` and
   `error.category == "permission-denied"`.
3. allowlist violation: the collector is run against a session with an
   EMPTY allowlist -> `status == "failed"` and
   `error.category == "guard-violation"`, and the operation is never
   *dispatched* (i.e. never reaches the point a real boto3 client would be
   called) — only *attempted*.

`tests/test_legacy_collectors.py` (Task 6.2) and
`tests/test_legacy_collector_outcomes.py` (Task 6.3) already cover a
representative sample of record shapes and the `_map_client_error` table;
this file makes that coverage exhaustive across all 25 capabilities.
"""

from __future__ import annotations

from typing import Any

import pytest
from botocore.exceptions import ClientError

from agentic.legacy_collectors import build_legacy_collector
from agentic.legacy_contracts import LEGACY_CAPABILITY_SPECS
from agentic.models import CollectorOutcome, StructuredError
from agentic.session import GuardViolationError


class FakeGuardedSession:
    """
    Minimal GuardedSession stand-in shared by the Task 6.2/6.3 test files.

    Tracks two things separately:
    - `calls`: every operation *attempted* (recorded before the allowlist
      check, mirroring `GuardedSessionImpl.call()`'s fail-closed order).
    - `dispatched`: operations that *passed* the allowlist check, i.e. would
      have reached a real boto3 client. An operation outside the allowlist
      never appears here.
    """

    def __init__(self, responses: dict[str, Any], allowed_operations: set[str]) -> None:
        self._responses = responses
        self._allowed = frozenset(allowed_operations)
        self.calls: list[str] = []
        self.dispatched: list[str] = []

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
        self.dispatched.append(key)
        if key not in self._responses:
            raise KeyError(f"No scripted response for {key}")
        response = self._responses[key]
        if isinstance(response, Exception):
            raise response
        return response


def _client_error(code: str, message: str = "boom") -> ClientError:
    return ClientError(
        error_response={"Error": {"Code": code, "Message": message}},
        operation_name="SomeOperation",
    )


# ---------------------------------------------------------------------------
# Minimal valid success response per capability_id x allowed_operation.
#
# Shapes are the smallest dicts each `collect_*` function (see
# `agentic/legacy_collectors.py`) needs to run to completion without a
# KeyError, verified by reading each function's field access.
# ---------------------------------------------------------------------------

_SUCCESS_RESPONSES: dict[str, dict[str, Any]] = {
    "billing.summary": {
        "ce:GetCostAndUsage": {
            "ResultsByTime": [
                {
                    "Total": {
                        "UnblendedCost": {"Amount": "10.0"},
                        "BlendedCost": {"Amount": "10.0"},
                    },
                    "TimePeriod": {"Start": "2024-01-01"},
                    "Groups": [
                        {"Keys": ["AmazonEC2"], "Metrics": {"UnblendedCost": {"Amount": "5.0"}}}
                    ],
                }
            ]
        },
    },
    "s3.inventory": {
        "s3:ListBuckets": {"Buckets": [{"Name": "bucket-a", "CreationDate": None}]},
        "s3:GetBucketLifecycleConfiguration": {"Rules": []},
        "s3:GetBucketVersioning": {"Status": "Enabled"},
        "s3:GetBucketEncryption": {},
    },
    "ebs.inventory": {
        "ec2:DescribeVolumes": {
            "Volumes": [
                {"VolumeId": "vol-1", "Size": 8, "VolumeType": "gp3", "State": "available"}
            ]
        },
    },
    "efs.inventory": {
        "efs:DescribeFileSystems": {
            "FileSystems": [
                {
                    "FileSystemId": "fs-1",
                    "CreationTime": None,
                    "LifeCycleState": "available",
                    "NumberOfMountTargets": 1,
                    "SizeInBytes": {"Value": 100},
                }
            ]
        },
    },
    "backup.inventory": {
        "backup:ListBackupVaults": {
            "BackupVaultList": [{"BackupVaultName": "vault-1", "BackupVaultArn": "arn:1"}]
        },
        "backup:ListBackupPlans": {
            "BackupPlansList": [
                {"BackupPlanId": "plan-1", "BackupPlanName": "plan-1", "VersionId": "v1"}
            ]
        },
    },
    "vpc.inventory": {
        "ec2:DescribeVpcs": {
            "Vpcs": [{"VpcId": "vpc-1", "CidrBlock": "10.0.0.0/16", "State": "available"}]
        },
    },
    "nat.inventory": {
        "ec2:DescribeNatGateways": {
            "NatGateways": [
                {"NatGatewayId": "nat-1", "VpcId": "vpc-1", "SubnetId": "subnet-1", "State": "available"}
            ]
        },
    },
    "cloudfront.inventory": {
        "cloudfront:ListDistributions": {
            "DistributionList": {
                "Items": [
                    {"Id": "dist-1", "DomainName": "d.cloudfront.net", "Status": "Deployed", "Enabled": True}
                ],
                "IsTruncated": False,
            }
        },
    },
    "route53.inventory": {
        "route53:ListHostedZones": {
            "HostedZones": [{"Id": "/hostedzone/Z1", "Name": "example.com.", "Config": {}}]
        },
    },
    "nlb.inventory": {
        "elasticloadbalancing:DescribeLoadBalancers": {
            "LoadBalancers": [
                {
                    "LoadBalancerName": "lb-1",
                    "LoadBalancerArn": "arn:lb1",
                    "Type": "network",
                    "DNSName": "lb1.aws",
                    "Scheme": "internet-facing",
                    "State": {"Code": "active"},
                    "VpcId": "vpc-1",
                    "AvailabilityZones": [{"ZoneName": "us-east-1a"}],
                }
            ]
        },
        "elasticloadbalancing:DescribeListeners": {"Listeners": []},
    },
    "rds.inventory": {
        "rds:DescribeDBInstances": {
            "DBInstances": [
                {
                    "DBInstanceIdentifier": "db-1",
                    "Engine": "postgres",
                    "DBInstanceClass": "db.t3.micro",
                    "DBInstanceStatus": "available",
                }
            ]
        },
    },
    "dynamodb.inventory": {
        "dynamodb:ListTables": {"TableNames": ["table-1"]},
        "dynamodb:DescribeTable": {"Table": {"TableName": "table-1", "TableStatus": "ACTIVE"}},
    },
    "elasticache.inventory": {
        "elasticache:DescribeCacheClusters": {
            "CacheClusters": [
                {
                    "CacheClusterId": "cache-1",
                    "Engine": "redis",
                    "EngineVersion": "6.2",
                    "CacheNodeType": "cache.t3.micro",
                    "CacheClusterStatus": "available",
                    "NumCacheNodes": 1,
                }
            ]
        },
    },
    "sns.inventory": {
        "sns:ListTopics": {"Topics": [{"TopicArn": "arn:aws:sns:us-east-1:111:topic-1"}]},
        "sns:GetTopicAttributes": {"Attributes": {"DisplayName": "Topic 1"}},
    },
    "msk.inventory": {
        "kafka:ListClustersV2": {
            "ClusterInfoList": [
                {"ClusterName": "cluster-1", "ClusterArn": "arn:cluster1", "ClusterType": "PROVISIONED", "State": "ACTIVE"}
            ]
        },
    },
    "amazonmq.inventory": {
        "mq:ListBrokers": {
            "BrokerSummaries": [
                {
                    "BrokerId": "broker-1",
                    "BrokerName": "broker-1",
                    "BrokerState": "RUNNING",
                    "DeploymentMode": "SINGLE_INSTANCE",
                    "EngineType": "ActiveMQ",
                }
            ]
        },
    },
    "glue.inventory": {
        "glue:GetDatabases": {"DatabaseList": [{"Name": "db-1"}]},
        "glue:GetJobs": {"Jobs": [{"Name": "job-1"}]},
    },
    "cloudwatch.inventory": {
        "cloudwatch:DescribeAlarms": {
            "MetricAlarms": [
                {
                    "AlarmName": "alarm-1",
                    "StateValue": "OK",
                    "MetricName": "CPUUtilization",
                    "Namespace": "AWS/EC2",
                    "ActionsEnabled": True,
                }
            ]
        },
    },
    "cloudtrail.inventory": {
        "cloudtrail:DescribeTrails": {"trailList": [{"Name": "trail-1", "TrailARN": "arn:trail1"}]},
        "cloudtrail:GetTrailStatus": {"IsLogging": True},
    },
    "config.inventory": {
        "config:DescribeConfigurationRecorders": {
            "ConfigurationRecorders": [{"name": "recorder-1", "roleARN": "arn:role1"}]
        },
        "config:DescribeConfigurationRecorderStatus": {
            "ConfigurationRecordersStatus": [{"recording": True}]
        },
    },
    "kms.inventory": {
        "kms:ListKeys": {"Keys": [{"KeyId": "key-1"}]},
        "kms:DescribeKey": {
            "KeyMetadata": {
                "KeyId": "key-1",
                "Arn": "arn:key1",
                "KeyState": "Enabled",
                "Enabled": True,
                "CreationDate": None,
                "KeyManager": "CUSTOMER",
            }
        },
    },
    "waf.inventory": {
        "wafv2:ListWebACLs": {"WebACLs": [{"Name": "acl-1", "Id": "id-1", "ARN": "arn:acl1"}]},
    },
    "secretsmanager.inventory": {
        "secretsmanager:ListSecrets": {
            "SecretList": [{"Name": "secret-1", "ARN": "arn:secret1"}]
        },
    },
    "iam.inventory": {
        "iam:GetAccountSummary": {"SummaryMap": {"Users": 1, "AccountMFAEnabled": 1}},
        "iam:GetAccountPasswordPolicy": {"PasswordPolicy": {"MinimumPasswordLength": 8}},
    },
    "cost-optimization.findings": {
        "ec2:DescribeAddresses": {"Addresses": []},
        "elasticloadbalancing:DescribeTargetGroups": {"TargetGroups": []},
        "elasticloadbalancing:DescribeTargetHealth": {"TargetHealthDescriptions": []},
        "pricing:GetProducts": {"PriceList": []},
    },
}

_SPECS_BY_ID = {spec.capability_id: spec for spec in LEGACY_CAPABILITY_SPECS}
_ALL_CAPABILITY_IDS = list(_SPECS_BY_ID)


def test_success_response_table_covers_every_capability_and_operation() -> None:
    """Sanity check on the data table itself before it drives the matrix below."""
    assert set(_SUCCESS_RESPONSES) == set(_SPECS_BY_ID)
    for capability_id, spec in _SPECS_BY_ID.items():
        assert set(spec.allowed_operations) <= set(_SUCCESS_RESPONSES[capability_id]), (
            f"{capability_id}: missing scripted response for one of its allowed_operations"
        )


@pytest.fixture(autouse=True)
def isolate_pricing_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    `cost-optimization.findings` resolves pricing via
    `utils.pricing._load_cache`/`_save_to_cache`, which read/write
    `data-pricing/extracted/<region>.json` on the real filesystem. Stub both
    so this test file never touches that directory (hermetic).
    """
    monkeypatch.setattr("utils.pricing._load_cache", lambda region: None)
    monkeypatch.setattr("utils.pricing._save_to_cache", lambda region, data: None)


@pytest.mark.parametrize("capability_id", _ALL_CAPABILITY_IDS)
def test_collector_success(capability_id: str) -> None:
    """All allowed_operations mocked with a valid response -> succeeded."""
    spec = _SPECS_BY_ID[capability_id]
    session = FakeGuardedSession(
        responses=_SUCCESS_RESPONSES[capability_id],
        allowed_operations=set(spec.allowed_operations),
    )
    collector = build_legacy_collector(capability_id)

    outcome = collector.collect(capability_id, "1.0.0", "111111111111", "us-east-1", {}, session)

    assert isinstance(outcome, CollectorOutcome)
    assert outcome.status == "succeeded", outcome.error


@pytest.mark.parametrize("capability_id", _ALL_CAPABILITY_IDS)
def test_collector_access_denied(capability_id: str) -> None:
    """The capability's primary (first) allowed operation raising AccessDenied -> permission-denied."""
    spec = _SPECS_BY_ID[capability_id]
    primary_op = spec.allowed_operations[0]
    session = FakeGuardedSession(
        responses={primary_op: _client_error("AccessDenied")},
        allowed_operations=set(spec.allowed_operations),
    )
    collector = build_legacy_collector(capability_id)

    outcome = collector.collect(capability_id, "1.0.0", "111111111111", "us-east-1", {}, session)

    assert outcome.status == "failed"
    assert outcome.error is not None
    assert outcome.error.category == "permission-denied"


@pytest.mark.parametrize("capability_id", _ALL_CAPABILITY_IDS)
def test_collector_allowlist_violation(capability_id: str) -> None:
    """Empty allowlist -> guard-violation, and the op is never dispatched (only attempted)."""
    session = FakeGuardedSession(responses={}, allowed_operations=set())
    collector = build_legacy_collector(capability_id)

    outcome = collector.collect(capability_id, "1.0.0", "111111111111", "us-east-1", {}, session)

    assert outcome.status == "failed"
    assert outcome.error is not None
    assert outcome.error.category == "guard-violation"
    assert len(session.calls) > 0, "expected at least one attempted operation"
    assert session.dispatched == [], "no operation should ever pass the allowlist check"
