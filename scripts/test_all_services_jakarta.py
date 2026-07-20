"""
Scan semua service yang sudah dimigrasikan di region ap-southeast-3 (Jakarta).
Jalankan lewat agentic legacy_adapter — full GuardedSession path.
"""
import boto3
from agentic.legacy_adapter import run_legacy_capability, SERVICE_TO_CAPABILITY

# Setup
session = boto3.Session(region_name="ap-southeast-3")
sts = session.client("sts")
identity = sts.get_caller_identity()
account_id = identity["Account"]
region = "ap-southeast-3"

print(f"Account : {account_id}")
print(f"Region  : {region} (Jakarta)")
print(f"ARN     : {identity['Arn']}")
print()
print("=" * 60)
print(f"Scan semua service ({len(SERVICE_TO_CAPABILITY)} capabilities)")
print("=" * 60)

assessment_data: dict = {"services": {}}
results: dict[str, str] = {}

for service_code in sorted(SERVICE_TO_CAPABILITY.keys()):
    print(f"\n[{service_code}] ...", end=" ", flush=True)
    try:
        run_legacy_capability(
            service_code=service_code,
            session=session,
            account_id=account_id,
            region=region,
            assessment_data=assessment_data,
        )
        svc_data = assessment_data["services"].get(service_code, {})
        count = svc_data.get("count", 0) if isinstance(svc_data, dict) else "?"
        results[service_code] = f"OK ({count} items)"
        print(f"✓ {count} items")
    except Exception as e:
        results[service_code] = f"ERROR: {type(e).__name__}: {str(e)[:80]}"
        print(f"✗ {type(e).__name__}: {str(e)[:80]}")

# Ringkasan
print("\n")
print("=" * 60)
print("RINGKASAN")
print("=" * 60)
ok_count = sum(1 for v in results.values() if v.startswith("OK"))
err_count = len(results) - ok_count
for svc, status in sorted(results.items()):
    icon = "✓" if status.startswith("OK") else "✗"
    print(f"  {icon} {svc:<20} {status}")
print(f"\nTotal: {ok_count}/{len(results)} berhasil, {err_count} gagal")
