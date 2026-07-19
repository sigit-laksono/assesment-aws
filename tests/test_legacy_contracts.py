"""
Tests for legacy capability allowlist/schema registration (Task 6.1).

Covers:
- Every legacy capability spec registers without error.
- Every registered capability has non-empty input/output schema refs
  and a non-empty, exact (no wildcard) allowed_operations set (Req 7.3, 13.1).
- allowed_operations exactly matches the operations actually called by the
  corresponding collectors/*.py source (spot-checked per capability).
- No duplicate capability_id across specs.
"""

from __future__ import annotations

import pytest

from agentic.legacy_contracts import (
    LEGACY_CAPABILITY_SPECS,
    build_legacy_descriptor,
    register_all_legacy_capabilities,
)
from agentic.registry import CapabilityRegistryImpl


class TestLegacyCapabilitySpecs:
    """Structural checks on the spec table itself."""

    def test_no_duplicate_capability_ids(self) -> None:
        ids = [spec.capability_id for spec in LEGACY_CAPABILITY_SPECS]
        assert len(ids) == len(set(ids)), "Duplicate capability_id in legacy specs"

    def test_every_spec_has_nonempty_allowlist(self) -> None:
        for spec in LEGACY_CAPABILITY_SPECS:
            assert len(spec.allowed_operations) > 0, (
                f"{spec.capability_id} has empty allowed_operations"
            )

    def test_no_wildcard_operations(self) -> None:
        for spec in LEGACY_CAPABILITY_SPECS:
            for op in spec.allowed_operations:
                assert "*" not in op, f"{spec.capability_id} declares wildcard '{op}'"
                assert ":" in op, f"{spec.capability_id} operation '{op}' not service:operation"

    def test_expected_capability_ids_present(self) -> None:
        expected = {
            "billing.summary",
            "s3.inventory",
            "ebs.inventory",
            "efs.inventory",
            "backup.inventory",
            "vpc.inventory",
            "nat.inventory",
            "cloudfront.inventory",
            "route53.inventory",
            "nlb.inventory",
            "rds.inventory",
            "dynamodb.inventory",
            "elasticache.inventory",
            "sns.inventory",
            "msk.inventory",
            "amazonmq.inventory",
            "glue.inventory",
            "cloudwatch.inventory",
            "cloudtrail.inventory",
            "config.inventory",
            "kms.inventory",
            "waf.inventory",
            "secretsmanager.inventory",
            "iam.inventory",
            "cost-optimization.findings",
        }
        actual = {spec.capability_id for spec in LEGACY_CAPABILITY_SPECS}
        assert actual == expected

    @pytest.mark.parametrize(
        "capability_id,expected_ops",
        [
            ("billing.summary", {"ce:GetCostAndUsage"}),
            (
                "s3.inventory",
                {
                    "s3:ListBuckets",
                    "s3:GetBucketLifecycleConfiguration",
                    "s3:GetBucketVersioning",
                    "s3:GetBucketEncryption",
                },
            ),
            ("ebs.inventory", {"ec2:DescribeVolumes"}),
            ("efs.inventory", {"efs:DescribeFileSystems"}),
            ("backup.inventory", {"backup:ListBackupVaults", "backup:ListBackupPlans"}),
            ("vpc.inventory", {"ec2:DescribeVpcs"}),
            ("nat.inventory", {"ec2:DescribeNatGateways"}),
            ("cloudfront.inventory", {"cloudfront:ListDistributions"}),
            ("route53.inventory", {"route53:ListHostedZones"}),
            (
                "nlb.inventory",
                {
                    "elasticloadbalancing:DescribeLoadBalancers",
                    "elasticloadbalancing:DescribeListeners",
                },
            ),
            ("rds.inventory", {"rds:DescribeDBInstances"}),
            ("dynamodb.inventory", {"dynamodb:ListTables", "dynamodb:DescribeTable"}),
            ("elasticache.inventory", {"elasticache:DescribeCacheClusters"}),
            ("sns.inventory", {"sns:ListTopics", "sns:GetTopicAttributes"}),
            ("msk.inventory", {"kafka:ListClustersV2"}),
            ("amazonmq.inventory", {"mq:ListBrokers"}),
            ("glue.inventory", {"glue:GetDatabases", "glue:GetJobs"}),
            ("cloudwatch.inventory", {"cloudwatch:DescribeAlarms"}),
            ("cloudtrail.inventory", {"cloudtrail:DescribeTrails", "cloudtrail:GetTrailStatus"}),
            (
                "config.inventory",
                {
                    "config:DescribeConfigurationRecorders",
                    "config:DescribeConfigurationRecorderStatus",
                },
            ),
            ("kms.inventory", {"kms:ListKeys", "kms:DescribeKey"}),
            ("waf.inventory", {"wafv2:ListWebACLs"}),
            ("secretsmanager.inventory", {"secretsmanager:ListSecrets"}),
            ("iam.inventory", {"iam:GetAccountSummary", "iam:GetAccountPasswordPolicy"}),
            (
                "cost-optimization.findings",
                {
                    "ec2:DescribeAddresses",
                    "elasticloadbalancing:DescribeTargetGroups",
                    "elasticloadbalancing:DescribeTargetHealth",
                    "pricing:GetProducts",
                },
            ),
        ],
    )
    def test_allowlist_matches_legacy_code(
        self, capability_id: str, expected_ops: set[str]
    ) -> None:
        """allowed_operations must exactly match what collectors/*.py calls today."""
        spec = next(
            s for s in LEGACY_CAPABILITY_SPECS if s.capability_id == capability_id
        )
        assert set(spec.allowed_operations) == expected_ops


class TestLegacyDescriptor:
    """Checks on the CapabilityDescriptor built from a spec."""

    def test_descriptor_has_schema_refs(self) -> None:
        for spec in LEGACY_CAPABILITY_SPECS:
            descriptor = build_legacy_descriptor(spec)
            assert descriptor.input_schema_ref != ""
            assert descriptor.output_schema_ref != ""
            assert descriptor.error_schema_ref == "structured-error/1.0.0"

    def test_descriptor_permissions_equal_allowlist(self) -> None:
        for spec in LEGACY_CAPABILITY_SPECS:
            descriptor = build_legacy_descriptor(spec)
            assert set(descriptor.permissions) == set(spec.allowed_operations)

    def test_descriptor_scope_is_valid(self) -> None:
        for spec in LEGACY_CAPABILITY_SPECS:
            descriptor = build_legacy_descriptor(spec)
            assert descriptor.scope in ("global", "regional", "derived")


class TestRegisterAllLegacyCapabilities:
    """Integration: all specs register into a fresh registry without error."""

    def test_registers_without_error(self) -> None:
        registry = CapabilityRegistryImpl()
        register_all_legacy_capabilities(registry)
        manifest = registry.snapshot()
        registered_ids = {cap.capability_id for cap in manifest.capabilities}
        expected_ids = {spec.capability_id for spec in LEGACY_CAPABILITY_SPECS}
        assert registered_ids == expected_ids

    def test_each_registered_capability_has_nonempty_allowlist(self) -> None:
        registry = CapabilityRegistryImpl()
        register_all_legacy_capabilities(registry)
        manifest = registry.snapshot()
        for cap in manifest.capabilities:
            assert len(cap.allowed_operations) > 0, (
                f"{cap.capability_id} missing allowed_operations after registration"
            )

    def test_resolve_returns_registered_entry(self) -> None:
        registry = CapabilityRegistryImpl()
        register_all_legacy_capabilities(registry)
        result = registry.resolve("s3.inventory", "1.0.0")
        assert not hasattr(result, "code")  # not a StructuredError
        assert result.descriptor.capability_id == "s3.inventory"
