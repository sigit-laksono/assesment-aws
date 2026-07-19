"""
Legacy Collectors — GuardedSession-backed collect() functions (Task 6.2).

One `collect_*` function per legacy capability_id (matching the 25 specs in
`agentic/legacy_contracts.py`). Each function:

- Accepts a `GuardedSession` (agentic.session.GuardedSessionImpl or any
  object exposing `.call(service, operation, **kwargs)`) instead of a raw
  boto3 session/client.
- Calls AWS exclusively through `session.call(service, operation, **kwargs)`
  — never `session.client(...)` directly — so every operation is checked
  against the capability's allowlist before dispatch (Req 7.1, 7.2).
- Takes NO shared mutable `assessment_data` dict. Each function returns its
  own result (a list of normalized record dicts, or a single summary dict
  for capabilities whose legacy shape was a single object) (Req 8.1).

Operation naming: `allowed_operations` in `agentic/legacy_contracts.py`
(Task 6.1, frozen) uses IAM-action-style PascalCase (e.g. "s3:ListBuckets"),
matching the `permissions` field convention and the existing Task 5 test
suite (`tests/test_session_factory.py` calls `guarded.call("ec2",
"DescribeInstances", ...)`). Every `session.call()` invocation below uses
that same PascalCase operation name so the allowlist check in
`GuardedSessionImpl.call()` matches.

ponytail: `GuardedSessionImpl.call()` (Task 5, frozen) does
`getattr(client, operation)`, which requires boto3's snake_case method
names to dispatch correctly against a REAL boto3 client — PascalCase
`getattr(client, "ListBuckets")` raises AttributeError there. This is a
latent casing mismatch between the frozen allowlist convention and the
frozen dispatch implementation, pre-existing before this task. Fixing it
is a `GuardedSessionImpl`/Task-5 concern, not this migration; per user
direction this module matches the allowlist's PascalCase convention and
leaves the dispatch-side reconciliation for later.

Scope boundary (Task 6.2 vs 6.3): the `collect_*` functions in this module
still return plain records or raise exceptions
(`botocore.exceptions.ClientError`, `agentic.session.GuardViolationError`)
on failure — that part is unchanged from Task 6.2. Task 6.3 adds a thin
wrapping layer (`_run_collector`, `_map_client_error`,
`_to_resource_records`) around the `Collector`-protocol adapter classes
below, so `.collect()` returns `CollectorOutcome` instead of plain
records/exceptions.

`collect_cost_optimization_findings` is a derived collector: it takes the
already-collected ebs/ec2/s3/alb/nlb records as explicit parameters (not a
shared dict) plus a GuardedSession for its own direct AWS calls
(ec2:DescribeAddresses, elbv2 target group/health, pricing:GetProducts).

This module does NOT replace or modify `collectors/*.py` — those remain
wired to the legacy interactive wizard (`aws_assessment.py`) unchanged
until Task 8.2's adapter. It also does NOT modify `utils/pricing.py`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from botocore.exceptions import ClientError

from agentic.models import (
    CollectorOutcome,
    Evidence,
    ResourceRecord,
    StructuredError,
    TargetPair,
)
from agentic.session import GuardViolationError
from utils.pricing import _merge as _merge_pricing  # reuse reference merge logic


# ---------------------------------------------------------------------------
# Pagination helpers (GuardedSession exposes only `.call()`, no paginators)
# ---------------------------------------------------------------------------


def _paginate_next_token(
    session: Any, service: str, operation: str, items_key: str, **kwargs: Any
) -> list[dict[str, Any]]:
    """Flat NextToken-style pagination (ec2 describe_* operations)."""
    items: list[dict[str, Any]] = []
    token: str | None = None
    while True:
        call_kwargs = dict(kwargs)
        if token:
            call_kwargs["NextToken"] = token
        response = session.call(service, operation, **call_kwargs)
        items.extend(response.get(items_key, []))
        token = response.get("NextToken")
        if not token:
            return items


def _paginate_marker(
    session: Any,
    service: str,
    operation: str,
    items_key: str,
    request_key: str = "Marker",
    response_key: str = "NextMarker",
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Flat Marker/NextMarker-style pagination (route53, elbv2)."""
    items: list[dict[str, Any]] = []
    marker: str | None = None
    while True:
        call_kwargs = dict(kwargs)
        if marker:
            call_kwargs[request_key] = marker
        response = session.call(service, operation, **call_kwargs)
        items.extend(response.get(items_key, []))
        marker = response.get(response_key)
        if not marker:
            return items


def _fmt(dt: Any) -> str:
    """Format a datetime the same way the legacy collectors did, else pass through."""
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return dt if dt is not None else "N/A"


# ---------------------------------------------------------------------------
# collectors/billing.py — billing.summary
# ---------------------------------------------------------------------------


def collect_billing_summary(session: Any) -> dict[str, Any]:
    """
    Migrated from `collectors/billing.py::get_billing_data()`.

    Calls ce:GetCostAndUsage twice (ungrouped totals + grouped-by-service)
    via `session.call()`.

    ponytail: the legacy code pinned the Cost Explorer client to
    region_name='us-east-1' (CE is a single-region API). GuardedSession.call()
    dispatches through whichever region the underlying boto3 Session already
    has — no per-call region override exists yet. Unchanged from how every
    other regional collector already uses session.call(); fixing that is an
    Session/Executor-layer concern, not this migration.
    """
    from datetime import date, timedelta

    end_date = date.today().replace(day=1)
    start_date = (end_date - timedelta(days=1)).replace(day=1)
    time_period = {
        "Start": start_date.strftime("%Y-%m-%d"),
        "End": end_date.strftime("%Y-%m-%d"),
    }

    response_total = session.call(
        "ce",
        "GetCostAndUsage",
        TimePeriod=time_period,
        Granularity="MONTHLY",
        Metrics=["UnblendedCost", "BlendedCost"],
    )
    response_grouped = session.call(
        "ce",
        "GetCostAndUsage",
        TimePeriod=time_period,
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
    )

    total_cost_actual = 0.0
    total_cost_blended = 0.0
    if response_total["ResultsByTime"]:
        result = response_total["ResultsByTime"][0]
        total_cost_actual = float(result["Total"]["UnblendedCost"]["Amount"])
        total_cost_blended = float(result["Total"]["BlendedCost"]["Amount"])

    monthly_costs = []
    service_costs: dict[str, list[dict[str, Any]]] = {}
    for result in response_grouped["ResultsByTime"]:
        period = result["TimePeriod"]["Start"]
        total_cost = 0.0
        for group in result["Groups"]:
            service = group["Keys"][0]
            cost = float(group["Metrics"]["UnblendedCost"]["Amount"])
            if cost > 0:
                service_costs.setdefault(service, []).append(
                    {"period": period, "cost": cost}
                )
                total_cost += cost
        monthly_costs.append({
            "period": period,
            "total": total_cost_actual if total_cost_actual > 0 else total_cost,
        })

    total_by_service = {
        service: sum(c["cost"] for c in costs)
        for service, costs in service_costs.items()
    }
    top_services = sorted(total_by_service.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "monthly_costs": monthly_costs,
        "service_costs": service_costs,
        "period": f"Bulan Lalu: {start_date.strftime('%B %Y')}",
        "total_actual": total_cost_actual,
        "total_blended": total_cost_blended,
        "top_services": top_services,
    }


# ---------------------------------------------------------------------------
# collectors/storage.py — s3.inventory, ebs.inventory, efs.inventory,
# backup.inventory
# ---------------------------------------------------------------------------


def collect_s3_inventory(session: Any) -> list[dict[str, Any]]:
    """Migrated from `collectors/storage.py::inventory_s3()`."""
    buckets = session.call("s3", "ListBuckets")
    bucket_list: list[dict[str, Any]] = []

    for bucket in buckets["Buckets"]:
        name = bucket["Name"]

        try:
            lc = session.call("s3", "GetBucketLifecycleConfiguration", Bucket=name)
            has_lifecycle = len(lc.get("Rules", [])) > 0
        except ClientError as e:
            has_lifecycle = (
                False if e.response["Error"]["Code"] == "NoSuchLifecycleConfiguration" else None
            )

        try:
            ver = session.call("s3", "GetBucketVersioning", Bucket=name)
            versioning_status = ver.get("Status", "Never") or "Never"
        except ClientError:
            versioning_status = None

        try:
            session.call("s3", "GetBucketEncryption", Bucket=name)
            encrypted = True
        except ClientError:
            encrypted = False

        bucket_list.append({
            "name": name,
            "creation_date": _fmt(bucket["CreationDate"]),
            "has_lifecycle": has_lifecycle,
            "versioning_status": versioning_status,
            "encrypted": encrypted,
        })

    return bucket_list


def collect_ebs_inventory(session: Any) -> list[dict[str, Any]]:
    """Migrated from `collectors/storage.py::inventory_ebs()`."""
    volumes = _paginate_next_token(session, "ec2", "DescribeVolumes", "Volumes")
    volume_list: list[dict[str, Any]] = []

    for volume in volumes:
        attachments = volume.get("Attachments", [])
        attached_instance = attachments[0]["InstanceId"] if attachments else None
        volume_list.append({
            "id": volume["VolumeId"],
            "size": volume["Size"],
            "type": volume["VolumeType"],
            "state": volume["State"],
            "iops": volume.get("Iops", "N/A"),
            "encrypted": volume.get("Encrypted", False),
            "attached_instance": attached_instance,
            "throughput": volume.get("Throughput", None),
            "name": next(
                (t["Value"] for t in volume.get("Tags", []) if t["Key"] == "Name"), ""
            ),
            "snapshot_id": volume.get("SnapshotId", ""),
        })

    return volume_list


def collect_efs_inventory(session: Any) -> list[dict[str, Any]]:
    """Migrated from `collectors/storage.py::inventory_efs()`."""
    file_systems = session.call("efs", "DescribeFileSystems")
    fs_list: list[dict[str, Any]] = []

    for fs in file_systems.get("FileSystems", []):
        fs_list.append({
            "id": fs["FileSystemId"],
            "name": fs.get("Name", "N/A"),
            "creation_time": _fmt(fs["CreationTime"]),
            "life_cycle_state": fs["LifeCycleState"],
            "number_of_mount_targets": fs["NumberOfMountTargets"],
            "size_in_bytes": fs["SizeInBytes"]["Value"],
            "encrypted": fs.get("Encrypted", False),
        })

    return fs_list


def collect_backup_inventory(session: Any) -> dict[str, list[dict[str, Any]]]:
    """Migrated from `collectors/storage.py::inventory_backup()`."""
    vaults = session.call("backup", "ListBackupVaults")
    vault_list = [
        {
            "name": vault["BackupVaultName"],
            "arn": vault["BackupVaultArn"],
            "creation_date": _fmt(vault.get("CreationDate")),
            "number_of_recovery_points": vault.get("NumberOfRecoveryPoints", 0),
        }
        for vault in vaults.get("BackupVaultList", [])
    ]

    plans = session.call("backup", "ListBackupPlans")
    plan_list = [
        {
            "id": plan["BackupPlanId"],
            "name": plan["BackupPlanName"],
            "version_id": plan["VersionId"],
            "creation_date": _fmt(plan.get("CreationDate")),
        }
        for plan in plans.get("BackupPlansList", [])
    ]

    return {"vaults": vault_list, "plans": plan_list}


# ---------------------------------------------------------------------------
# collectors/network.py — vpc.inventory, nat.inventory, cloudfront.inventory,
# route53.inventory, nlb.inventory
# ---------------------------------------------------------------------------


def collect_vpc_inventory(session: Any) -> list[dict[str, Any]]:
    """Migrated from `collectors/network.py::inventory_vpc()`."""
    vpcs = _paginate_next_token(session, "ec2", "DescribeVpcs", "Vpcs")
    vpc_list: list[dict[str, Any]] = []

    for vpc in vpcs:
        vpc_name = "N/A"
        for tag in vpc.get("Tags", []):
            if tag["Key"] == "Name":
                vpc_name = tag["Value"]
                break
        vpc_list.append({
            "id": vpc["VpcId"],
            "name": vpc_name,
            "cidr": vpc["CidrBlock"],
            "is_default": vpc.get("IsDefault", False),
            "state": vpc["State"],
        })

    return vpc_list


def collect_nat_inventory(session: Any) -> list[dict[str, Any]]:
    """Migrated from `collectors/network.py::inventory_nat_gateway()`."""
    nats = _paginate_next_token(session, "ec2", "DescribeNatGateways", "NatGateways")
    return [
        {
            "id": nat["NatGatewayId"],
            "vpc_id": nat["VpcId"],
            "subnet_id": nat["SubnetId"],
            "state": nat["State"],
            "connectivity_type": nat.get("ConnectivityType", "public"),
        }
        for nat in nats
    ]


def collect_cloudfront_inventory(session: Any) -> list[dict[str, Any]]:
    """Migrated from `collectors/network.py::inventory_cloudfront()`."""
    dist_list: list[dict[str, Any]] = []
    marker: str | None = None

    while True:
        kwargs: dict[str, Any] = {}
        if marker:
            kwargs["Marker"] = marker
        response = session.call("cloudfront", "ListDistributions", **kwargs)
        distribution_list = response.get("DistributionList", {}) or {}
        for dist in distribution_list.get("Items", []) or []:
            dist_list.append({
                "id": dist["Id"],
                "domain": dist["DomainName"],
                "status": dist["Status"],
                "enabled": dist["Enabled"],
            })
        if not distribution_list.get("IsTruncated"):
            return dist_list
        marker = distribution_list.get("NextMarker")
        if not marker:
            return dist_list


def collect_route53_inventory(session: Any) -> list[dict[str, Any]]:
    """Migrated from `collectors/network.py::inventory_route53()`."""
    zones = _paginate_marker(session, "route53", "ListHostedZones", "HostedZones")
    return [
        {
            "id": zone["Id"].split("/")[-1],
            "name": zone["Name"],
            "type": "Private" if zone.get("Config", {}).get("PrivateZone", False) else "Public",
            "record_count": zone.get("ResourceRecordSetCount", 0),
            "comment": zone.get("Config", {}).get("Comment", "N/A"),
        }
        for zone in zones
    ]


def collect_nlb_inventory(session: Any) -> list[dict[str, Any]]:
    """Migrated from `collectors/network.py::inventory_nlb()`."""
    load_balancers = _paginate_marker(
        session, "elasticloadbalancing", "DescribeLoadBalancers", "LoadBalancers"
    )
    nlb_list: list[dict[str, Any]] = []

    for lb in load_balancers:
        if lb["Type"] != "network":
            continue

        listener_count = 0
        try:
            listeners_resp = session.call(
                "elasticloadbalancing",
                "DescribeListeners",
                LoadBalancerArn=lb["LoadBalancerArn"],
            )
            listener_count = len(listeners_resp.get("Listeners", []))
        except ClientError:
            pass

        nlb_list.append({
            "name": lb["LoadBalancerName"],
            "arn": lb["LoadBalancerArn"],
            "dns": lb["DNSName"],
            "scheme": lb["Scheme"],
            "state": lb["State"]["Code"],
            "vpc_id": lb["VpcId"],
            "availability_zones": [az["ZoneName"] for az in lb["AvailabilityZones"]],
            "listener_count": listener_count,
        })

    return nlb_list


# ---------------------------------------------------------------------------
# collectors/database.py — rds.inventory, dynamodb.inventory,
# elasticache.inventory
# ---------------------------------------------------------------------------


def collect_rds_inventory(session: Any) -> list[dict[str, Any]]:
    """Migrated from `collectors/database.py::inventory_rds()`."""
    instances = session.call("rds", "DescribeDBInstances")
    return [
        {
            "id": instance["DBInstanceIdentifier"],
            "engine": instance["Engine"],
            "class": instance["DBInstanceClass"],
            "status": instance["DBInstanceStatus"],
            "engine_version": instance.get("EngineVersion", ""),
            "multi_az": instance.get("MultiAZ", False),
            "storage_type": instance.get("StorageType", ""),
            "allocated_storage": instance.get("AllocatedStorage", 0),
            "storage_encrypted": instance.get("StorageEncrypted", False),
            "backup_retention": instance.get("BackupRetentionPeriod", 0),
            "publicly_accessible": instance.get("PubliclyAccessible", False),
            "deletion_protection": instance.get("DeletionProtection", False),
        }
        for instance in instances["DBInstances"]
    ]


def collect_dynamodb_inventory(session: Any) -> list[dict[str, Any]]:
    """Migrated from `collectors/database.py::inventory_dynamodb()`."""
    tables = session.call("dynamodb", "ListTables")
    table_list: list[dict[str, Any]] = []

    for table_name in tables.get("TableNames", []):
        try:
            table_info = session.call("dynamodb", "DescribeTable", TableName=table_name)
            table = table_info["Table"]
            table_list.append({
                "name": table["TableName"],
                "status": table["TableStatus"],
                "item_count": table.get("ItemCount", 0),
                "size_bytes": table.get("TableSizeBytes", 0),
            })
        except ClientError:
            pass

    return table_list


def collect_elasticache_inventory(session: Any) -> list[dict[str, Any]]:
    """Migrated from `collectors/database.py::inventory_elasticache()`."""
    clusters = session.call("elasticache", "DescribeCacheClusters")
    return [
        {
            "id": cluster["CacheClusterId"],
            "engine": cluster["Engine"],
            "engine_version": cluster["EngineVersion"],
            "node_type": cluster["CacheNodeType"],
            "status": cluster["CacheClusterStatus"],
            "num_nodes": cluster["NumCacheNodes"],
        }
        for cluster in clusters.get("CacheClusters", [])
    ]


# ---------------------------------------------------------------------------
# collectors/integration.py — sns.inventory, msk.inventory,
# amazonmq.inventory, glue.inventory, cloudwatch.inventory
# ---------------------------------------------------------------------------


def collect_sns_inventory(session: Any) -> list[dict[str, Any]]:
    """Migrated from `collectors/integration.py::inventory_sns()`."""
    topics = session.call("sns", "ListTopics")
    topic_list: list[dict[str, Any]] = []

    for topic in topics.get("Topics", []):
        topic_arn = topic["TopicArn"]
        try:
            attrs = session.call("sns", "GetTopicAttributes", TopicArn=topic_arn)
            attributes = attrs["Attributes"]
            topic_list.append({
                "arn": topic_arn,
                "name": topic_arn.split(":")[-1],
                "display_name": attributes.get("DisplayName", "N/A"),
                "subscriptions_confirmed": attributes.get("SubscriptionsConfirmed", "0"),
                "subscriptions_pending": attributes.get("SubscriptionsPending", "0"),
            })
        except ClientError:
            pass

    return topic_list


def collect_msk_inventory(session: Any) -> list[dict[str, Any]]:
    """Migrated from `collectors/integration.py::inventory_msk()`."""
    clusters = session.call("kafka", "ListClustersV2")
    return [
        {
            "name": cluster["ClusterName"],
            "arn": cluster["ClusterArn"],
            "cluster_type": cluster["ClusterType"],
            "state": cluster["State"],
            "creation_time": _fmt(cluster.get("CreationTime")),
        }
        for cluster in clusters.get("ClusterInfoList", [])
    ]


def collect_amazonmq_inventory(session: Any) -> list[dict[str, Any]]:
    """Migrated from `collectors/integration.py::inventory_amazonmq()`."""
    brokers = session.call("mq", "ListBrokers")
    return [
        {
            "id": broker["BrokerId"],
            "name": broker["BrokerName"],
            "broker_state": broker["BrokerState"],
            "deployment_mode": broker["DeploymentMode"],
            "engine_type": broker["EngineType"],
            "host_instance_type": broker.get("HostInstanceType", "N/A"),
            "created": _fmt(broker.get("Created")),
        }
        for broker in brokers.get("BrokerSummaries", [])
    ]


def collect_glue_inventory(session: Any) -> dict[str, list[dict[str, Any]]]:
    """Migrated from `collectors/integration.py::inventory_glue()`."""
    databases = session.call("glue", "GetDatabases")
    db_list = [
        {
            "name": db["Name"],
            "description": db.get("Description", "N/A"),
            "create_time": _fmt(db.get("CreateTime")),
        }
        for db in databases.get("DatabaseList", [])
    ]

    jobs = session.call("glue", "GetJobs")
    job_list = [
        {
            "name": job["Name"],
            "role": job.get("Role", "N/A"),
            "created_on": _fmt(job.get("CreatedOn")),
            "glue_version": job.get("GlueVersion", "N/A"),
            "max_capacity": job.get("MaxCapacity", "N/A"),
        }
        for job in jobs.get("Jobs", [])
    ]

    return {"databases": db_list, "jobs": job_list}


def collect_cloudwatch_inventory(session: Any) -> list[dict[str, Any]]:
    """Migrated from `collectors/integration.py::inventory_cloudwatch()`."""
    alarms = session.call("cloudwatch", "DescribeAlarms")
    return [
        {
            "name": alarm["AlarmName"],
            "state": alarm["StateValue"],
            "metric": alarm["MetricName"],
            "namespace": alarm["Namespace"],
            "actions_enabled": alarm["ActionsEnabled"],
        }
        for alarm in alarms.get("MetricAlarms", [])
    ]


# ---------------------------------------------------------------------------
# collectors/operations.py — cloudtrail.inventory, config.inventory
# ---------------------------------------------------------------------------


def collect_cloudtrail_inventory(session: Any) -> list[dict[str, Any]]:
    """Migrated from `collectors/operations.py::inventory_cloudtrail()`."""
    trails = session.call("cloudtrail", "DescribeTrails")
    trail_list: list[dict[str, Any]] = []

    for trail in trails.get("trailList", []):
        try:
            status = session.call("cloudtrail", "GetTrailStatus", Name=trail["TrailARN"])
            is_logging = status.get("IsLogging", False)
        except ClientError:
            is_logging = False

        trail_list.append({
            "name": trail["Name"],
            "arn": trail["TrailARN"],
            "is_logging": is_logging,
            "is_multi_region": trail.get("IsMultiRegionTrail", False),
            "s3_bucket": trail.get("S3BucketName", "N/A"),
        })

    return trail_list


def collect_config_inventory(session: Any) -> list[dict[str, Any]]:
    """Migrated from `collectors/operations.py::inventory_config()`."""
    recorders = session.call("config", "DescribeConfigurationRecorders")
    recorder_list: list[dict[str, Any]] = []

    for recorder in recorders.get("ConfigurationRecorders", []):
        try:
            status_response = session.call(
                "config",
                "DescribeConfigurationRecorderStatus",
                ConfigurationRecorderNames=[recorder["name"]],
            )
            status = status_response["ConfigurationRecordersStatus"][0]
            is_recording = status.get("recording", False)
        except ClientError:
            is_recording = False

        recorder_list.append({
            "name": recorder["name"],
            "role_arn": recorder.get("roleARN", "N/A"),
            "is_recording": is_recording,
            "record_all": recorder.get("recordingGroup", {}).get("allSupported", False),
        })

    return recorder_list


# ---------------------------------------------------------------------------
# collectors/security.py — kms.inventory, waf.inventory,
# secretsmanager.inventory, iam.inventory
# ---------------------------------------------------------------------------


def collect_kms_inventory(session: Any) -> list[dict[str, Any]]:
    """Migrated from `collectors/security.py::inventory_kms()`."""
    keys = session.call("kms", "ListKeys")
    key_list: list[dict[str, Any]] = []

    for key in keys.get("Keys", []):
        try:
            key_metadata = session.call("kms", "DescribeKey", KeyId=key["KeyId"])
            metadata = key_metadata["KeyMetadata"]
            if metadata["KeyManager"] == "AWS":
                continue
            key_list.append({
                "id": metadata["KeyId"],
                "arn": metadata["Arn"],
                "state": metadata["KeyState"],
                "enabled": metadata["Enabled"],
                "created_date": _fmt(metadata["CreationDate"]),
            })
        except ClientError:
            pass

    return key_list


def collect_waf_inventory(session: Any) -> list[dict[str, Any]]:
    """Migrated from `collectors/security.py::inventory_waf()`."""
    acl_list: list[dict[str, Any]] = []

    regional_acls = session.call("wafv2", "ListWebACLs", Scope="REGIONAL")
    for acl in regional_acls.get("WebACLs", []):
        acl_list.append({
            "name": acl["Name"],
            "id": acl["Id"],
            "arn": acl["ARN"],
            "scope": "REGIONAL",
        })

    try:
        cloudfront_acls = session.call("wafv2", "ListWebACLs", Scope="CLOUDFRONT")
        for acl in cloudfront_acls.get("WebACLs", []):
            acl_list.append({
                "name": acl["Name"],
                "id": acl["Id"],
                "arn": acl["ARN"],
                "scope": "CLOUDFRONT",
            })
    except ClientError:
        pass

    return acl_list


def collect_secretsmanager_inventory(session: Any) -> list[dict[str, Any]]:
    """Migrated from `collectors/security.py::inventory_secretsmanager()`."""
    secrets = session.call("secretsmanager", "ListSecrets")
    return [
        {
            "name": secret["Name"],
            "arn": secret["ARN"],
            "description": secret.get("Description", "N/A"),
            "last_changed_date": _fmt(secret.get("LastChangedDate")),
            "last_accessed_date": _fmt(secret.get("LastAccessedDate")),
            "rotation_enabled": secret.get("RotationEnabled", False),
        }
        for secret in secrets.get("SecretList", [])
    ]


def collect_iam_inventory(session: Any) -> dict[str, Any]:
    """Migrated from `collectors/security.py::inventory_iam()`."""
    summary = session.call("iam", "GetAccountSummary").get("SummaryMap", {})
    root_mfa_enabled = bool(summary.get("AccountMFAEnabled", 0))

    try:
        policy = session.call("iam", "GetAccountPasswordPolicy").get(
            "PasswordPolicy", {}
        )
        password_policy_set = True
    except ClientError:
        policy = {}
        password_policy_set = False

    return {
        "users_count": summary.get("Users", 0),
        "groups_count": summary.get("Groups", 0),
        "roles_count": summary.get("Roles", 0),
        "policies_count": summary.get("Policies", 0),
        "mfa_devices_in_use": summary.get("MFADevicesInUse", 0),
        "account_access_keys": summary.get("AccountAccessKeysPresent", 0),
        "root_mfa_enabled": root_mfa_enabled,
        "password_policy_set": password_policy_set,
        "min_password_length": policy.get("MinimumPasswordLength", 0),
        "require_symbols": policy.get("RequireSymbols", False),
        "require_numbers": policy.get("RequireNumbers", False),
        "require_uppercase": policy.get("RequireUppercaseCharacters", False),
        "require_lowercase": policy.get("RequireLowercaseCharacters", False),
        "password_reuse_prevention": policy.get("PasswordReusePrevention", 0),
        "max_password_age": policy.get("MaxPasswordAge", 0),
    }


# ---------------------------------------------------------------------------
# collectors/cost_optimization.py — cost-optimization.findings (derived)
# ---------------------------------------------------------------------------
#
# Derived/aggregate collector: rules 1, 2, 5, 6, 7, 8 read already-collected
# records from other capabilities (ebs, ec2, s3, alb/nlb) instead of calling
# AWS directly. Only EIP-idle (rule 3) and LB-without-target (rule 4) make
# direct AWS calls, plus the pricing lookup. All are migrated to
# `session.call()` below. Record field names match the plain-dict shapes
# produced by this module's own `collect_ebs_inventory`/`collect_s3_inventory`
# /`collect_nlb_inventory` and by the pre-existing `collectors/compute.py`
# (`instances` list, `alb` load_balancers list) — unchanged from the legacy
# `assessment_data['services'][x]` sub-structures, just passed as explicit
# parameters instead of shared-dict lookups (Req 7.1, 7.2, 8.1).

_HOURS_PER_MONTH = 730
_EBS_DEFAULT_PRICE = 0.10

_GRAVITON_MAP = {
    "m5": ("m7g", 30), "m5a": ("m7g", 28),
    "c5": ("c7g", 35), "c5a": ("c7g", 30),
    "r5": ("r7g", 25), "r5a": ("r7g", 22),
    "t3": ("t4g", 20), "t3a": ("t4g", 18),
}

_PUBLIC_IPV4_MONTHLY = 3.60


def _ebs_monthly_cost(size_gb: int, vol_type: str, pricing: dict) -> float:
    price = pricing["ebs"].get(vol_type, _EBS_DEFAULT_PRICE)
    return round(size_gb * price, 2)


def _fetch_pricing_via_session(session: Any, region: str) -> dict[str, Any] | None:
    """
    Same AWS calls as `utils.pricing.fetch_pricing()`, dispatched through
    `session.call("pricing", "GetProducts", ...)` instead of a raw
    `session.client('pricing').get_products(...)` (Req 7.1).
    """
    import json as _json

    from utils.pricing import _EBS_VOLUME_TYPES, _region_prefix

    result: dict[str, Any] = {}

    ebs: dict[str, float] = {}
    for vol_type in _EBS_VOLUME_TYPES:
        try:
            resp = session.call(
                "pricing", "GetProducts",
                ServiceCode="AmazonEC2",
                Filters=[
                    {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Storage"},
                    {"Type": "TERM_MATCH", "Field": "regionCode", "Value": region},
                    {"Type": "TERM_MATCH", "Field": "volumeApiName", "Value": vol_type},
                ],
                MaxResults=1,
            )
            for item_str in resp.get("PriceList", []):
                item = _json.loads(item_str)
                for term in item.get("terms", {}).get("OnDemand", {}).values():
                    for pd in term.get("priceDimensions", {}).values():
                        usd = pd.get("pricePerUnit", {}).get("USD")
                        if usd:
                            ebs[vol_type] = round(float(usd), 6)
        except Exception:
            pass
    if ebs:
        result["ebs"] = ebs

    try:
        resp = session.call(
            "pricing", "GetProducts",
            ServiceCode="AmazonVPC",
            Filters=[
                {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "IP Address"},
                {"Type": "TERM_MATCH", "Field": "regionCode", "Value": region},
            ],
            MaxResults=10,
        )
        for item_str in resp.get("PriceList", []):
            item = _json.loads(item_str)
            usage = (item.get("product", {}).get("attributes", {}).get("usagetype", "") or "").lower()
            if "idleaddress" in usage:
                for term in item.get("terms", {}).get("OnDemand", {}).values():
                    for pd in term.get("priceDimensions", {}).values():
                        usd = pd.get("pricePerUnit", {}).get("USD")
                        if usd and float(usd) > 0:
                            result["eip_hr"] = round(float(usd), 6)
    except Exception:
        pass

    for service_code, family, key in (
        ("AWSELB", "Load Balancer-Application", "alb_hr"),
        ("AWSELB", "Load Balancer-Network", "nlb_hr"),
    ):
        try:
            resp = session.call(
                "pricing", "GetProducts",
                ServiceCode=service_code,
                Filters=[
                    {"Type": "TERM_MATCH", "Field": "productFamily", "Value": family},
                    {"Type": "TERM_MATCH", "Field": "regionCode", "Value": region},
                    {"Type": "TERM_MATCH", "Field": "usagetype", "Value": f"{_region_prefix(region)}-LoadBalancerUsage"},
                ],
                MaxResults=1,
            )
            for item_str in resp.get("PriceList", []):
                item = _json.loads(item_str)
                for term in item.get("terms", {}).get("OnDemand", {}).values():
                    for pd in term.get("priceDimensions", {}).values():
                        usd = pd.get("pricePerUnit", {}).get("USD")
                        if usd and float(usd) > 0:
                            result[key] = round(float(usd), 6)
        except Exception:
            pass

    return result or None


def _resolve_pricing_via_session(session: Any, region: str) -> tuple[dict, str]:
    """Guarded-session equivalent of `utils.pricing.resolve_pricing()`."""
    from utils.pricing import _load_cache, _save_to_cache

    try:
        api_data = _fetch_pricing_via_session(session, region)
        if api_data:
            _save_to_cache(region, api_data)
    except Exception:
        pass

    cached = _load_cache(region)
    return _merge_pricing(cached, region)


def _rule_ebs_unattached(ebs_volumes: Sequence[Mapping[str, Any]], findings: list, pricing: dict) -> None:
    for vol in ebs_volumes:
        if vol.get("state") == "available":
            cost = _ebs_monthly_cost(vol.get("size", 0), vol.get("type", ""), pricing)
            findings.append({
                "rule": "ebs_unattached",
                "category": "EBS Unattached",
                "resource_id": vol["id"],
                "details": f"{vol.get('size')} GB  ·  {vol.get('type')}  ·  "
                           f"{'Encrypted' if vol.get('encrypted') else 'Not encrypted'}",
                "estimated_monthly_cost": cost,
                "severity": "medium",
                "action": "Hapus volume atau buat snapshot lalu delete",
            })


def _rule_ec2_stopped_ebs(
    ec2_instances: Sequence[Mapping[str, Any]],
    ebs_volumes: Sequence[Mapping[str, Any]],
    findings: list,
    pricing: dict,
) -> None:
    if not ec2_instances or not ebs_volumes:
        return
    stopped_ids = {inst["id"] for inst in ec2_instances if inst.get("state") == "stopped"}
    if not stopped_ids:
        return
    for vol in ebs_volumes:
        if vol.get("attached_instance") in stopped_ids:
            cost = _ebs_monthly_cost(vol.get("size", 0), vol.get("type", ""), pricing)
            findings.append({
                "rule": "ec2_stopped_ebs",
                "category": "EC2 Stopped (EBS masih berjalan)",
                "resource_id": vol["id"],
                "details": f"Attached ke instance {vol['attached_instance']} (stopped)  ·  "
                           f"{vol.get('size')} GB  ·  {vol.get('type')}",
                "estimated_monthly_cost": cost,
                "severity": "medium",
                "action": "Terminate instance atau detach & snapshot volume",
            })


def _rule_eip_idle(session: Any, findings: list, pricing: dict) -> None:
    eip_monthly = round(pricing["eip_hr"] * _HOURS_PER_MONTH, 2)
    response = session.call("ec2", "DescribeAddresses")
    for addr in response.get("Addresses", []):
        if not addr.get("AssociationId"):
            findings.append({
                "rule": "eip_idle",
                "category": "Elastic IP Idle",
                "resource_id": addr.get("AllocationId", addr.get("PublicIp", "N/A")),
                "details": f"Public IP: {addr.get('PublicIp', 'N/A')}  ·  tidak ter-assign",
                "estimated_monthly_cost": eip_monthly,
                "severity": "low",
                "action": "Release Elastic IP jika tidak digunakan",
            })


def _rule_lb_no_target(
    session: Any,
    load_balancers: Sequence[Mapping[str, Any]],
    findings: list,
    pricing: dict,
) -> None:
    """`load_balancers` entries: {'arn', 'name', 'type': 'ALB'|'NLB'}."""
    alb_monthly = round(pricing["alb_hr"] * _HOURS_PER_MONTH, 2)
    nlb_monthly = round(pricing["nlb_hr"] * _HOURS_PER_MONTH, 2)
    price_by_type = {"ALB": alb_monthly, "NLB": nlb_monthly}

    for lb in load_balancers:
        price = price_by_type.get(lb["type"], 0)
        try:
            tg_arns: list[str] = []
            marker: str | None = None
            while True:
                kwargs: dict[str, Any] = {"LoadBalancerArn": lb["arn"]}
                if marker:
                    kwargs["Marker"] = marker
                page = session.call("elasticloadbalancing", "DescribeTargetGroups", **kwargs)
                tg_arns.extend(tg["TargetGroupArn"] for tg in page.get("TargetGroups", []))
                marker = page.get("NextMarker")
                if not marker:
                    break

            if not tg_arns:
                findings.append({
                    "rule": "lb_no_target",
                    "category": f"{lb['type']} Tanpa Target",
                    "resource_id": lb["name"],
                    "details": "Tidak memiliki target group",
                    "estimated_monthly_cost": price,
                    "severity": "high",
                    "action": "Hapus load balancer jika tidak digunakan",
                })
                continue

            has_target = False
            for tg_arn in tg_arns:
                try:
                    health = session.call(
                        "elasticloadbalancing", "DescribeTargetHealth", TargetGroupArn=tg_arn
                    )
                    if health.get("TargetHealthDescriptions"):
                        has_target = True
                        break
                except ClientError:
                    pass

            if not has_target:
                findings.append({
                    "rule": "lb_no_target",
                    "category": f"{lb['type']} Tanpa Target",
                    "resource_id": lb["name"],
                    "details": f"{len(tg_arns)} target group terdaftar, tidak ada target aktif",
                    "estimated_monthly_cost": price,
                    "severity": "high",
                    "action": "Hapus load balancer atau tambahkan target aktif",
                })
        except ClientError:
            pass


def _get_instance_family(instance_type: str) -> str:
    parts = instance_type.split(".")
    return parts[0] if parts else ""


def _rule_graviton_eligible(
    ec2_instances: Sequence[Mapping[str, Any]], findings: list, pricing: dict
) -> None:
    for inst in ec2_instances:
        platform = inst.get("platform", "")
        arch = inst.get("architecture", "")
        inst_type = inst.get("type", "")
        family = _get_instance_family(inst_type)

        if platform.lower() == "windows" or arch != "x86_64" or family not in _GRAVITON_MAP:
            continue

        graviton_target_family, savings_pct = _GRAVITON_MAP[family]
        size_part = inst_type.split(".", 1)[1] if "." in inst_type else "xlarge"
        graviton_target = f"{graviton_target_family}.{size_part}"

        estimated_savings_usd = 0
        ec2_pricing = pricing.get("ec2_ondemand", {})
        current_price = ec2_pricing.get(inst_type, 0)
        if current_price > 0:
            estimated_savings_usd = round(current_price * _HOURS_PER_MONTH * (savings_pct / 100), 2)

        name = inst.get("name") or inst["id"]
        findings.append({
            "rule": "graviton_eligible",
            "category": "Graviton Migration Opportunity",
            "resource_id": inst["id"],
            "details": f"{name}  ·  {inst_type} → {graviton_target}  ·  "
                       f"{inst.get('platform', 'Linux')}  ·  est. savings {savings_pct}%",
            "estimated_monthly_cost": estimated_savings_usd,
            "severity": "medium",
            "action": "Validasi kompatibilitas aplikasi sebelum migrasi ke Graviton",
        })


def _rule_public_ipv4_cost(ec2_instances: Sequence[Mapping[str, Any]], findings: list) -> None:
    for inst in ec2_instances:
        public_ip = inst.get("public_ip")
        if public_ip is None:
            continue
        name = inst.get("name") or inst["id"]
        findings.append({
            "rule": "public_ipv4_cost",
            "category": "Public IPv4 Cost",
            "resource_id": inst["id"],
            "details": f"{name}  ·  IP: {public_ip}  ·  {inst.get('type', '')}",
            "estimated_monthly_cost": _PUBLIC_IPV4_MONTHLY,
            "severity": "low",
            "action": "Review apakah instance perlu public IP atau bisa pakai private + LB",
        })


def _rule_s3_no_lifecycle(s3_buckets: Sequence[Mapping[str, Any]], findings: list) -> None:
    for bucket in s3_buckets:
        if bucket.get("has_lifecycle") is False:
            findings.append({
                "rule": "s3_no_lifecycle",
                "category": "S3 Missing Lifecycle Policy",
                "resource_id": bucket["name"],
                "details": f"{bucket['name']}  ·  Tidak ada lifecycle rule  ·  "
                           f"versioning: {bucket.get('versioning_status', 'Unknown')}",
                "estimated_monthly_cost": 0,
                "severity": "medium",
                "action": "Tambahkan lifecycle rule: transisi ke S3-IA setelah 30 hari, Glacier setelah 90 hari",
            })


def _rule_s3_versioning_no_expiry(s3_buckets: Sequence[Mapping[str, Any]], findings: list) -> None:
    for bucket in s3_buckets:
        if bucket.get("versioning_status") == "Enabled" and bucket.get("has_lifecycle") is False:
            findings.append({
                "rule": "s3_versioning_no_expiry",
                "category": "S3 Versioning Without Expiry",
                "resource_id": bucket["name"],
                "details": f"{bucket['name']}  ·  Versioning aktif tanpa expiry rule  ·  "
                           f"storage bisa 2-5x lebih besar dari yang terlihat",
                "estimated_monthly_cost": 0,
                "severity": "high",
                "action": "Tambahkan NoncurrentVersionExpiration rule. Rekomendasi: hapus noncurrent version setelah 30-90 hari",
            })


def collect_cost_optimization_findings(
    session: Any,
    region: str,
    ebs_volumes: Sequence[Mapping[str, Any]] = (),
    ec2_instances: Sequence[Mapping[str, Any]] = (),
    s3_buckets: Sequence[Mapping[str, Any]] = (),
    load_balancers: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """
    Migrated from `collectors/cost_optimization.py::run_cost_optimization()`.

    Derived collector: `ebs_volumes`, `ec2_instances`, `s3_buckets`, and
    `load_balancers` are records already collected by other capabilities
    (ebs.inventory, ec2.inventory, s3.inventory, nlb.inventory / alb
    inventory) — passed explicitly instead of read from a shared
    `assessment_data` dict (Req 8.1). `session` is used only for this
    capability's own direct AWS calls: ec2:DescribeAddresses,
    elasticloadbalancing:DescribeTargetGroups/DescribeTargetHealth, and
    pricing:GetProducts (via `_resolve_pricing_via_session`).
    """
    pricing, _source = _resolve_pricing_via_session(session, region)

    findings: list[dict[str, Any]] = []
    _rule_ebs_unattached(ebs_volumes, findings, pricing)
    _rule_ec2_stopped_ebs(ec2_instances, ebs_volumes, findings, pricing)
    _rule_eip_idle(session, findings, pricing)
    _rule_lb_no_target(session, load_balancers, findings, pricing)
    _rule_graviton_eligible(ec2_instances, findings, pricing)
    _rule_public_ipv4_cost(ec2_instances, findings)
    _rule_s3_no_lifecycle(s3_buckets, findings)
    _rule_s3_versioning_no_expiry(s3_buckets, findings)

    return findings


# ---------------------------------------------------------------------------
# Error mapping (Req 8.1, 8.2, 9.1)
# ---------------------------------------------------------------------------

_PERMISSION_DENIED_CODES = frozenset({"AccessDenied", "UnauthorizedAccess", "AuthFailure"})
_THROTTLED_CODES = frozenset({"Throttling", "RequestLimitExceeded"})


def _map_client_error(
    exc: ClientError, capability_id: str, account_id: str, region_scope: str
) -> StructuredError:
    """
    Map a botocore ClientError to a StructuredError.

    AccessDenied/UnauthorizedAccess/AuthFailure -> permission-denied (Req 9.1).
    Throttling/RequestLimitExceeded -> throttled, retryable=True.
    Everything else -> internal, not retryable.
    """
    error_info = exc.response.get("Error", {}) if hasattr(exc, "response") else {}
    code = error_info.get("Code", type(exc).__name__)
    message = error_info.get("Message", "")

    if code in _PERMISSION_DENIED_CODES:
        category: str = "permission-denied"
        retryable = False
    elif code in _THROTTLED_CODES:
        category = "throttled"
        retryable = True
    else:
        category = "internal"
        retryable = False

    return StructuredError(
        code=code,
        category=category,  # type: ignore[arg-type]
        retryable=retryable,
        safe_message=f"{code}: {message}",
        capability_id=capability_id,
        account_id=account_id,
        region_scope=region_scope,
    )


# ---------------------------------------------------------------------------
# Record shaping (Req 8.1)
# ---------------------------------------------------------------------------
#
# `collect_*` functions return either a `list[dict]` (one ResourceRecord per
# item), a single flat summary `dict` (billing, iam — one ResourceRecord
# wrapping the whole dict), or a `dict` whose every value is itself a list
# (backup: vaults+plans, glue: databases+jobs — one ResourceRecord per item
# across all lists, tagged with a `record_type` field so the two kinds stay
# distinguishable after flattening).


def _record_identity(item: Mapping[str, Any], index: int) -> str:
    """Best-effort stable-ish identity from common id-like keys, else index."""
    for key in ("id", "name", "arn"):
        value = item.get(key)
        if value:
            return str(value)
    return str(index)


def _is_multi_list_dict(result: Mapping[str, Any]) -> bool:
    return len(result) > 0 and all(isinstance(v, list) for v in result.values())


def _to_resource_records(
    capability_id: str, account_id: str, region_scope: str, result: Any
) -> tuple[ResourceRecord, ...]:
    """Normalize a plain collect_*() result into a tuple of ResourceRecord."""
    if isinstance(result, list):
        items: list[tuple[str, Mapping[str, Any]]] = [
            (_record_identity(item, i), item) for i, item in enumerate(result)
        ]
    elif isinstance(result, dict) and _is_multi_list_dict(result):
        items = []
        for key, values in result.items():
            record_type = key[:-1] if key.endswith("s") else key
            for i, item in enumerate(values):
                identity = _record_identity(item, i)
                items.append((identity, {**item, "record_type": record_type}))
    elif isinstance(result, dict):
        # Single flat summary dict (e.g. billing.summary, iam.inventory).
        items = [("summary", result)]
    else:
        raise TypeError(f"Unsupported collect_* result type: {type(result)!r}")

    return tuple(
        ResourceRecord(
            resource_identity=f"{account_id}/{region_scope}/{capability_id}/{identity}",
            account_id=account_id,
            region_scope=region_scope,
            capability_id=capability_id,
            fields=fields,
        )
        for identity, fields in items
    )


def _build_evidence(
    capability_id: str, capability_version: str, account_id: str, region_scope: str
) -> Evidence:
    """
    One Evidence per outcome (not per record) — matches the CollectorOutcome
    shape's `evidence` tuple and the granularity ec2_collector.py uses.

    ponytail: `operation` records only the capability_id, not the exact list
    of AWS operations invoked, since the individual `collect_*` functions
    call `session.call()` multiple times internally and this adapter layer
    has no cheap way to observe which calls happened without instrumenting
    every collector. Upgrade path: have `collect_*` return the operations it
    used alongside its records if per-operation provenance is later required.
    """
    return Evidence(
        target=TargetPair(account_id=account_id, region_scope=region_scope),
        capability_id=capability_id,
        capability_version=capability_version,
        collector_version=capability_version,
        operation=f"legacy:{capability_id}",
        collected_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def _run_collector(
    capability_id: str,
    capability_version: str,
    account_id: str,
    region_scope: str,
    fn: Any,
) -> CollectorOutcome:
    """
    Shared try/except wrapping: run `fn()` (a closure over the underlying
    `collect_*` call) and translate its outcome/exception into a
    CollectorOutcome. Empty results are still `status="succeeded"`.
    """
    try:
        result = fn()
    except GuardViolationError as exc:
        return CollectorOutcome(status="failed", error=exc.error)
    except ClientError as exc:
        return CollectorOutcome(
            status="failed",
            error=_map_client_error(exc, capability_id, account_id, region_scope),
        )
    except Exception as exc:
        return CollectorOutcome(
            status="failed",
            error=StructuredError(
                code=type(exc).__name__,
                category="internal",
                retryable=False,
                safe_message=f"Unexpected error in collector: {type(exc).__name__}",
                capability_id=capability_id,
                account_id=account_id,
                region_scope=region_scope,
            ),
        )

    records = _to_resource_records(capability_id, account_id, region_scope, result)
    evidence = _build_evidence(capability_id, capability_version, account_id, region_scope)
    return CollectorOutcome(status="succeeded", records=records, evidence=(evidence,))


# ---------------------------------------------------------------------------
# Collector-protocol adapters (Req 7.1, 7.2, 8.1, 8.2, 9.1)
# ---------------------------------------------------------------------------
#
# Each adapter below satisfies `agentic.interfaces.Collector` structurally
# (a `.collect(capability_id, capability_version, account_id, region_scope,
# parameters, session)` method) so it can be registered against the
# capability manifest. `.collect()` returns `CollectorOutcome` — never a
# plain list/dict and never a boolean — via `_run_collector()` above.

# capability_id -> collect_*(session) function, for capabilities whose only
# input is the GuardedSession itself.
_SIMPLE_COLLECTOR_FUNCTIONS: dict[str, Any] = {
    "billing.summary": collect_billing_summary,
    "s3.inventory": collect_s3_inventory,
    "ebs.inventory": collect_ebs_inventory,
    "efs.inventory": collect_efs_inventory,
    "backup.inventory": collect_backup_inventory,
    "vpc.inventory": collect_vpc_inventory,
    "nat.inventory": collect_nat_inventory,
    "cloudfront.inventory": collect_cloudfront_inventory,
    "route53.inventory": collect_route53_inventory,
    "nlb.inventory": collect_nlb_inventory,
    "rds.inventory": collect_rds_inventory,
    "dynamodb.inventory": collect_dynamodb_inventory,
    "elasticache.inventory": collect_elasticache_inventory,
    "sns.inventory": collect_sns_inventory,
    "msk.inventory": collect_msk_inventory,
    "amazonmq.inventory": collect_amazonmq_inventory,
    "glue.inventory": collect_glue_inventory,
    "cloudwatch.inventory": collect_cloudwatch_inventory,
    "cloudtrail.inventory": collect_cloudtrail_inventory,
    "config.inventory": collect_config_inventory,
    "kms.inventory": collect_kms_inventory,
    "waf.inventory": collect_waf_inventory,
    "secretsmanager.inventory": collect_secretsmanager_inventory,
    "iam.inventory": collect_iam_inventory,
}


class LegacyRecordsCollector:
    """
    Structural `Collector` adapter for the 24 "simple" legacy capabilities
    (everything except the derived `cost-optimization.findings`).

    Dispatches to the matching `collect_*(session)` function and returns its
    result as-is (list or dict of plain records), using ONLY `session.call()`
    for AWS access and taking no shared mutable state.
    """

    def __init__(self, capability_id: str) -> None:
        if capability_id not in _SIMPLE_COLLECTOR_FUNCTIONS:
            raise ValueError(f"No migrated collector for '{capability_id}'")
        self._capability_id = capability_id
        self._fn = _SIMPLE_COLLECTOR_FUNCTIONS[capability_id]

    def collect(
        self,
        capability_id: str,
        capability_version: str,
        account_id: str,
        region_scope: str,
        parameters: Mapping[str, Any],
        session: Any,
    ) -> CollectorOutcome:
        return _run_collector(
            capability_id, capability_version, account_id, region_scope,
            lambda: self._fn(session),
        )


class CostOptimizationFindingsCollector:
    """
    Structural `Collector` adapter for the derived `cost-optimization.findings`
    capability. Already-collected sibling records (ebs/ec2/s3/load-balancer)
    are read from `parameters` (explicit input, not a shared dict) rather
    than from `assessment_data` (Req 8.1).
    """

    def collect(
        self,
        capability_id: str,
        capability_version: str,
        account_id: str,
        region_scope: str,
        parameters: Mapping[str, Any],
        session: Any,
    ) -> CollectorOutcome:
        region = parameters.get("region", region_scope)
        return _run_collector(
            capability_id, capability_version, account_id, region_scope,
            lambda: collect_cost_optimization_findings(
                session,
                region,
                ebs_volumes=parameters.get("ebs_volumes", ()),
                ec2_instances=parameters.get("ec2_instances", ()),
                s3_buckets=parameters.get("s3_buckets", ()),
                load_balancers=parameters.get("load_balancers", ()),
            ),
        )


def build_legacy_collector(capability_id: str) -> Any:
    """
    Factory returning the migrated Collector adapter for one legacy
    capability_id (Task 6.2). Used by `agentic/legacy_contracts.py` to
    register a real GuardedSession-backed implementation for each capability.
    """
    if capability_id == "cost-optimization.findings":
        return CostOptimizationFindingsCollector()
    return LegacyRecordsCollector(capability_id)
