"""
Test agentic EC2 collect — jalankan lewat GuardedSession ke AWS langsung.
"""
import boto3
from agentic.ec2_collector import EC2InventoryCollector
from agentic.ec2_contract import register_ec2_inventory
from agentic.registry import CapabilityRegistryImpl, RegisteredCapability
from agentic.session import GuardedSessionImpl, SessionIdentity

# 1. Cek credential
session = boto3.Session()
sts = session.client("sts")
identity = sts.get_caller_identity()
account_id = identity["Account"]
region = session.region_name or "ap-southeast-1"

print(f"Account : {account_id}")
print(f"Region  : {region}")
print(f"ARN     : {identity['Arn']}")
print()

# 2. Setup registry
registry = CapabilityRegistryImpl()
register_ec2_inventory(registry, EC2InventoryCollector())

resolved = registry.resolve("ec2.inventory")
assert isinstance(resolved, RegisteredCapability), "ec2.inventory tidak terdaftar!"

# 3. Bungkus session dengan GuardedSession (hanya ec2:DescribeInstances diizinkan)
guarded = GuardedSessionImpl(
    session=session,
    allowed_operations=set(resolved.descriptor.allowed_operations),
    identity=SessionIdentity(account_id=account_id),
)

# 4. Collect!
print("Menjalankan ec2.inventory lewat agentic collector...")
outcome = resolved.handler.collect(
    "ec2.inventory", account_id, region, {}, guarded
)

print(f"Status  : {outcome.status}")
print(f"Records : {len(outcome.records)}")

if outcome.status == "failed":
    print(f"Error   : {outcome.error.safe_message if outcome.error else 'unknown'}")
else:
    for r in outcome.records[:5]:  # tampilkan maks 5
        f = r.fields
        print(f"  - {f.get('instance_id')} | {f.get('instance_type')} | {f.get('state')} | {f.get('name')}")
    if len(outcome.records) > 5:
        print(f"  ... dan {len(outcome.records) - 5} instance lainnya")

if outcome.evidence:
    ev = outcome.evidence[0]
    print(f"\nEvidence:")
    print(f"  operation    : {ev.operation}")
    print(f"  collected_at : {ev.collected_at}")
    print(f"  target       : {ev.target.account_id}/{ev.target.region_scope}")
