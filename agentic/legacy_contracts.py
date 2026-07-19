"""
Legacy Capability Contracts — Allowlist and Schema Definitions.

Defines a CapabilityDescriptor for every AWS resource type currently
collected by the 8 legacy Collector modules (`collectors/billing.py`,
`storage.py`, `network.py`, `database.py`, `integration.py`,
`operations.py`, `security.py`, `cost_optimization.py`).

One capability is registered per AWS resource type / Collector function
(matching the existing `ec2.inventory@1.0.0` pattern and the capability
IDs already declared by `agentic/profiles/monthly_standard_v1.py`), not
one per legacy file. Capability IDs here intentionally mirror the
profile's `RequiredProfileItem.capability_id` values (e.g. `billing.summary`,
`nat.inventory`, `cloudwatch.inventory`, `cost-optimization.findings`)
so `monthly-standard@1.0.0` can resolve them once each becomes active.

`allowed_operations` lists ONLY AWS API operations actually invoked by the
current legacy Collector code (Req 7.3, 13.1) — no wildcard, no speculative
future operations. Each entry was verified by reading the corresponding
`collectors/*.py` source (see module docstring per section below).

This module defines the contract (descriptor + allowlist) and registers
each capability with its migrated Collector implementation from
`agentic/legacy_collectors.py` (Task 6.2), which calls AWS exclusively
through `GuardedSession.call()`.
"""

from __future__ import annotations

from typing import NamedTuple

from agentic.interfaces import Collector
from agentic.legacy_collectors import build_legacy_collector
from agentic.models import CapabilityDescriptor, SemVer
from agentic.registry import CapabilityRegistryImpl


# ---------------------------------------------------------------------------
# Spec type
# ---------------------------------------------------------------------------


class LegacyCapabilitySpec(NamedTuple):
    """One legacy capability's identity, scope, and read-only allowlist."""

    capability_id: str
    allowed_operations: tuple[str, ...]
    scope: str = "regional"  # "global" | "regional" | "derived"


# ---------------------------------------------------------------------------
# Specs — verified against collectors/*.py (see comments per source file)
# ---------------------------------------------------------------------------

LEGACY_CAPABILITY_SPECS: tuple[LegacyCapabilitySpec, ...] = (
    # --- collectors/billing.py: get_billing_data() -----------------------
    # ce.get_cost_and_usage() called twice (totals + grouped-by-service),
    # same operation both times.
    LegacyCapabilitySpec(
        capability_id="billing.summary",
        allowed_operations=("ce:GetCostAndUsage",),
        scope="global",
    ),
    # --- collectors/storage.py --------------------------------------------
    # inventory_s3(): list_buckets, get_bucket_lifecycle_configuration,
    # get_bucket_versioning, get_bucket_encryption.
    LegacyCapabilitySpec(
        capability_id="s3.inventory",
        allowed_operations=(
            "s3:ListBuckets",
            "s3:GetBucketLifecycleConfiguration",
            "s3:GetBucketVersioning",
            "s3:GetBucketEncryption",
        ),
        scope="global",
    ),
    # inventory_ebs(): ec2.describe_volumes (paginated).
    LegacyCapabilitySpec(
        capability_id="ebs.inventory",
        allowed_operations=("ec2:DescribeVolumes",),
        scope="regional",
    ),
    # inventory_efs(): efs.describe_file_systems.
    LegacyCapabilitySpec(
        capability_id="efs.inventory",
        allowed_operations=("efs:DescribeFileSystems",),
        scope="regional",
    ),
    # inventory_backup(): backup.list_backup_vaults, backup.list_backup_plans.
    LegacyCapabilitySpec(
        capability_id="backup.inventory",
        allowed_operations=("backup:ListBackupVaults", "backup:ListBackupPlans"),
        scope="regional",
    ),
    # --- collectors/network.py ---------------------------------------------
    # inventory_vpc(): ec2.describe_vpcs (paginated).
    LegacyCapabilitySpec(
        capability_id="vpc.inventory",
        allowed_operations=("ec2:DescribeVpcs",),
        scope="regional",
    ),
    # inventory_nat_gateway(): ec2.describe_nat_gateways (paginated).
    LegacyCapabilitySpec(
        capability_id="nat.inventory",
        allowed_operations=("ec2:DescribeNatGateways",),
        scope="regional",
    ),
    # inventory_cloudfront(): cloudfront.list_distributions (paginated).
    # CloudFront is a global (non-regional) service.
    LegacyCapabilitySpec(
        capability_id="cloudfront.inventory",
        allowed_operations=("cloudfront:ListDistributions",),
        scope="global",
    ),
    # inventory_route53(): route53.list_hosted_zones (paginated).
    # Route 53 is a global (non-regional) service.
    LegacyCapabilitySpec(
        capability_id="route53.inventory",
        allowed_operations=("route53:ListHostedZones",),
        scope="global",
    ),
    # inventory_nlb(): elbv2.describe_load_balancers (paginated),
    # elbv2.describe_listeners per load balancer.
    LegacyCapabilitySpec(
        capability_id="nlb.inventory",
        allowed_operations=(
            "elasticloadbalancing:DescribeLoadBalancers",
            "elasticloadbalancing:DescribeListeners",
        ),
        scope="regional",
    ),
    # --- collectors/database.py --------------------------------------------
    # inventory_rds(): rds.describe_db_instances.
    LegacyCapabilitySpec(
        capability_id="rds.inventory",
        allowed_operations=("rds:DescribeDBInstances",),
        scope="regional",
    ),
    # inventory_dynamodb(): dynamodb.list_tables, dynamodb.describe_table.
    LegacyCapabilitySpec(
        capability_id="dynamodb.inventory",
        allowed_operations=("dynamodb:ListTables", "dynamodb:DescribeTable"),
        scope="regional",
    ),
    # inventory_elasticache(): elasticache.describe_cache_clusters.
    LegacyCapabilitySpec(
        capability_id="elasticache.inventory",
        allowed_operations=("elasticache:DescribeCacheClusters",),
        scope="regional",
    ),
    # --- collectors/integration.py ------------------------------------------
    # inventory_sns(): sns.list_topics, sns.get_topic_attributes.
    LegacyCapabilitySpec(
        capability_id="sns.inventory",
        allowed_operations=("sns:ListTopics", "sns:GetTopicAttributes"),
        scope="regional",
    ),
    # inventory_msk(): kafka.list_clusters_v2.
    LegacyCapabilitySpec(
        capability_id="msk.inventory",
        allowed_operations=("kafka:ListClustersV2",),
        scope="regional",
    ),
    # inventory_amazonmq(): mq.list_brokers.
    LegacyCapabilitySpec(
        capability_id="amazonmq.inventory",
        allowed_operations=("mq:ListBrokers",),
        scope="regional",
    ),
    # inventory_glue(): glue.get_databases, glue.get_jobs.
    LegacyCapabilitySpec(
        capability_id="glue.inventory",
        allowed_operations=("glue:GetDatabases", "glue:GetJobs"),
        scope="regional",
    ),
    # inventory_cloudwatch(): cloudwatch.describe_alarms.
    LegacyCapabilitySpec(
        capability_id="cloudwatch.inventory",
        allowed_operations=("cloudwatch:DescribeAlarms",),
        scope="regional",
    ),
    # --- collectors/operations.py --------------------------------------------
    # inventory_cloudtrail(): cloudtrail.describe_trails, cloudtrail.get_trail_status.
    LegacyCapabilitySpec(
        capability_id="cloudtrail.inventory",
        allowed_operations=("cloudtrail:DescribeTrails", "cloudtrail:GetTrailStatus"),
        scope="regional",
    ),
    # inventory_config(): config.describe_configuration_recorders,
    # config.describe_configuration_recorder_status.
    LegacyCapabilitySpec(
        capability_id="config.inventory",
        allowed_operations=(
            "config:DescribeConfigurationRecorders",
            "config:DescribeConfigurationRecorderStatus",
        ),
        scope="regional",
    ),
    # --- collectors/security.py ----------------------------------------------
    # inventory_kms(): kms.list_keys, kms.describe_key.
    LegacyCapabilitySpec(
        capability_id="kms.inventory",
        allowed_operations=("kms:ListKeys", "kms:DescribeKey"),
        scope="regional",
    ),
    # inventory_waf(): wafv2.list_web_acls (called for Scope=REGIONAL and
    # again for Scope=CLOUDFRONT via a us-east-1 client) — same operation.
    LegacyCapabilitySpec(
        capability_id="waf.inventory",
        allowed_operations=("wafv2:ListWebACLs",),
        scope="regional",
    ),
    # inventory_secretsmanager(): secretsmanager.list_secrets.
    LegacyCapabilitySpec(
        capability_id="secretsmanager.inventory",
        allowed_operations=("secretsmanager:ListSecrets",),
        scope="regional",
    ),
    # inventory_iam(): iam.get_account_summary, iam.get_account_password_policy.
    LegacyCapabilitySpec(
        capability_id="iam.inventory",
        allowed_operations=("iam:GetAccountSummary", "iam:GetAccountPasswordPolicy"),
        scope="global",
    ),
    # --- collectors/cost_optimization.py --------------------------------------
    # run_cost_optimization(): ec2.describe_addresses (Rule 3 EIP idle);
    # elbv2.describe_target_groups (paginated) + elbv2.describe_target_health
    # (Rule 4 LB without target); PLUS utils.pricing.resolve_pricing(session, region)
    # -> fetch_pricing() calls session.client('pricing').get_products() four
    # times (EBS/EIP/ALB/NLB price lookups) using the SAME session argument —
    # this operation was missing from the initial manual-review draft and was
    # added after reading utils/pricing.py.
    LegacyCapabilitySpec(
        capability_id="cost-optimization.findings",
        allowed_operations=(
            "ec2:DescribeAddresses",
            "elasticloadbalancing:DescribeTargetGroups",
            "elasticloadbalancing:DescribeTargetHealth",
            "pricing:GetProducts",
        ),
        scope="derived",
    ),
)


# ---------------------------------------------------------------------------
# Placeholder handler (Task 6.2 replaces this with real Collectors)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def build_legacy_descriptor(spec: LegacyCapabilitySpec) -> CapabilityDescriptor:
    """
    Build the CapabilityDescriptor for one legacy capability spec.

    permissions is set equal to allowed_operations, matching the existing
    ec2.inventory@1.0.0 precedent (agentic/ec2_contract.py) where the
    declared IAM permission set and the read-only allowlist coincide.
    """
    return CapabilityDescriptor(
        schema_id="capability-descriptor",
        schema_version="1.0.0",
        capability_id=spec.capability_id,
        version=SemVer(1, 0, 0),
        input_schema_ref=f"{spec.capability_id}-input/1.0.0",
        output_schema_ref=f"{spec.capability_id}-output/1.0.0",
        error_schema_ref="structured-error/1.0.0",
        permissions=spec.allowed_operations,
        allowed_operations=spec.allowed_operations,
        prerequisites=(),
        support_status="active",
        scope=spec.scope,  # type: ignore[arg-type]
    )


def register_legacy_capability(
    registry: CapabilityRegistryImpl,
    spec: LegacyCapabilitySpec,
    collector: Collector,
) -> None:
    """Register a single legacy capability descriptor with its handler."""
    registry.register(build_legacy_descriptor(spec), collector)


def register_all_legacy_capabilities(registry: CapabilityRegistryImpl) -> None:
    """
    Register every legacy capability spec using its migrated
    GuardedSession-backed Collector (`agentic/legacy_collectors.py`,
    Task 6.2). Each Collector calls AWS exclusively through
    `GuardedSession.call()` and returns its own records rather than
    mutating a shared `assessment_data` dict.
    """
    for spec in LEGACY_CAPABILITY_SPECS:
        register_legacy_capability(
            registry, spec, build_legacy_collector(spec.capability_id)
        )
