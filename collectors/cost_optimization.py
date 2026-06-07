"""
Cost Optimization Collector
============================
Mendeteksi resource yang jelas-jelas terbuang (waste) — bukan right-sizing.
Scope: 4 rule dengan confidence tinggi (tidak ada false-positive):

  1. EBS Unattached        — volume state 'available', tidak dipakai siapapun
  2. EC2 Stopped + EBS     — instance mati tapi disk-nya masih dibayar
  3. Elastic IP Idle       — EIP tidak ter-assign ke resource manapun
  4. LB Tanpa Target       — ALB/NLB tidak punya target aktif, bayar fixed cost sia-sia

Pricing data diambil dari modul `utils.pricing` (terpisah, bisa di-scheduler).
"""
from utils.pricing import resolve_pricing

_HOURS_PER_MONTH = 730
_EBS_DEFAULT_PRICE = 0.10


def _ebs_monthly_cost(size_gb: int, vol_type: str, pricing: dict) -> float:
    price = pricing['ebs'].get(vol_type, _EBS_DEFAULT_PRICE)
    return round(size_gb * price, 2)


# ─── Rule 1: EBS Unattached ───────────────────────────────────────────────────

def _rule_ebs_unattached(assessment_data: dict, findings: list, pricing: dict):
    ebs = assessment_data.get('services', {}).get('ebs', {})
    for vol in ebs.get('volumes', []):
        if vol.get('state') == 'available':
            cost = _ebs_monthly_cost(vol.get('size', 0), vol.get('type', ''), pricing)
            findings.append({
                'rule':                   'ebs_unattached',
                'category':               'EBS Unattached',
                'resource_id':            vol['id'],
                'details':                f"{vol.get('size')} GB  ·  {vol.get('type')}  ·  "
                                          f"{'Encrypted' if vol.get('encrypted') else 'Not encrypted'}",
                'estimated_monthly_cost': cost,
                'severity':               'medium',
                'action':                 'Hapus volume atau buat snapshot lalu delete',
            })


# ─── Rule 2: EC2 Stopped + EBS Attached ──────────────────────────────────────

def _rule_ec2_stopped_ebs(assessment_data: dict, findings: list, pricing: dict):
    ec2_services = assessment_data.get('services', {}).get('ec2', {})
    ebs_services = assessment_data.get('services', {}).get('ebs', {})

    if not ec2_services or not ebs_services:
        return

    stopped_ids = {
        inst['id']
        for inst in ec2_services.get('instances', [])
        if inst.get('state') == 'stopped'
    }
    if not stopped_ids:
        return

    for vol in ebs_services.get('volumes', []):
        if vol.get('attached_instance') in stopped_ids:
            cost = _ebs_monthly_cost(vol.get('size', 0), vol.get('type', ''), pricing)
            findings.append({
                'rule':                   'ec2_stopped_ebs',
                'category':               'EC2 Stopped (EBS masih berjalan)',
                'resource_id':            vol['id'],
                'details':                f"Attached ke instance {vol['attached_instance']} (stopped)  ·  "
                                          f"{vol.get('size')} GB  ·  {vol.get('type')}",
                'estimated_monthly_cost': cost,
                'severity':               'medium',
                'action':                 'Terminate instance atau detach & snapshot volume',
            })


# ─── Rule 3: Elastic IP Idle ──────────────────────────────────────────────────

def _rule_eip_idle(session, findings: list, pricing: dict):
    eip_monthly = round(pricing['eip_hr'] * _HOURS_PER_MONTH, 2)
    try:
        ec2 = session.client('ec2')
        response = ec2.describe_addresses()
        for addr in response.get('Addresses', []):
            if not addr.get('AssociationId'):
                findings.append({
                    'rule':                   'eip_idle',
                    'category':               'Elastic IP Idle',
                    'resource_id':            addr.get('AllocationId', addr.get('PublicIp', 'N/A')),
                    'details':                f"Public IP: {addr.get('PublicIp', 'N/A')}  ·  tidak ter-assign",
                    'estimated_monthly_cost': eip_monthly,
                    'severity':               'low',
                    'action':                 'Release Elastic IP jika tidak digunakan',
                })
    except Exception as e:
        print(f"  ⚠ Tidak bisa cek Elastic IP: {e}")


# ─── Rule 4: Load Balancer Tanpa Target Aktif ─────────────────────────────────

def _rule_lb_no_target(session, assessment_data: dict, findings: list, pricing: dict):
    """Flag ALB/NLB tanpa target group atau tanpa target aktif."""
    alb_monthly = round(pricing['alb_hr'] * _HOURS_PER_MONTH, 2)
    nlb_monthly = round(pricing['nlb_hr'] * _HOURS_PER_MONTH, 2)

    lbs = []
    for svc_key, lb_type, price in [
        ('alb', 'ALB', alb_monthly),
        ('nlb', 'NLB', nlb_monthly),
    ]:
        for lb in assessment_data.get('services', {}).get(svc_key, {}).get('load_balancers', []):
            lbs.append({'arn': lb['arn'], 'name': lb['name'], 'type': lb_type, 'price': price})

    if not lbs:
        return

    try:
        elbv2 = session.client('elbv2')

        for lb in lbs:
            try:
                paginator = elbv2.get_paginator('describe_target_groups')
                tg_arns = []
                for page in paginator.paginate(LoadBalancerArn=lb['arn']):
                    tg_arns.extend([tg['TargetGroupArn'] for tg in page.get('TargetGroups', [])])

                if not tg_arns:
                    findings.append({
                        'rule':                   'lb_no_target',
                        'category':               f"{lb['type']} Tanpa Target",
                        'resource_id':            lb['name'],
                        'details':                'Tidak memiliki target group',
                        'estimated_monthly_cost': lb['price'],
                        'severity':               'high',
                        'action':                 'Hapus load balancer jika tidak digunakan',
                    })
                    continue

                has_target = False
                for tg_arn in tg_arns:
                    try:
                        health = elbv2.describe_target_health(TargetGroupArn=tg_arn)
                        if health.get('TargetHealthDescriptions'):
                            has_target = True
                            break
                    except Exception:
                        pass

                if not has_target:
                    findings.append({
                        'rule':                   'lb_no_target',
                        'category':               f"{lb['type']} Tanpa Target",
                        'resource_id':            lb['name'],
                        'details':                f"{len(tg_arns)} target group terdaftar, tidak ada target aktif",
                        'estimated_monthly_cost': lb['price'],
                        'severity':               'high',
                        'action':                 'Hapus load balancer atau tambahkan target aktif',
                    })

            except Exception as e:
                print(f"  ⚠ Tidak bisa cek target {lb['name']}: {e}")

    except Exception as e:
        print(f"  ⚠ Tidak bisa cek Load Balancer targets: {e}")


# ─── Rule 5: Graviton Eligible ────────────────────────────────────────────────

# Mapping: current family → (graviton target, savings percentage)
_GRAVITON_MAP = {
    'm5':  ('m7g', 30),
    'm5a': ('m7g', 28),
    'c5':  ('c7g', 35),
    'c5a': ('c7g', 30),
    'r5':  ('r7g', 25),
    'r5a': ('r7g', 22),
    't3':  ('t4g', 20),
    't3a': ('t4g', 18),
}


def _get_instance_family(instance_type: str) -> str:
    """Extract family from instance type, e.g. 'c5.2xlarge' → 'c5'."""
    parts = instance_type.split('.')
    return parts[0] if parts else ''


def _rule_graviton_eligible(assessment_data: dict, findings: list, pricing: dict):
    """Flag Linux x86_64 instances yang bisa migrasi ke Graviton."""
    ec2_services = assessment_data.get('services', {}).get('ec2', {})
    instances = ec2_services.get('instances', [])

    for inst in instances:
        platform = inst.get('platform', '')
        arch = inst.get('architecture', '')
        inst_type = inst.get('type', '')
        family = _get_instance_family(inst_type)

        # Hanya Linux + x86_64 + family ada di mapping
        if platform.lower() == 'windows':
            continue
        if arch != 'x86_64':
            continue
        if family not in _GRAVITON_MAP:
            continue

        graviton_target_family, savings_pct = _GRAVITON_MAP[family]
        # Build target type: replace family prefix
        size_part = inst_type.split('.', 1)[1] if '.' in inst_type else 'xlarge'
        graviton_target = f"{graviton_target_family}.{size_part}"

        # Estimasi savings — try pricing engine, default 0
        estimated_savings_usd = 0
        try:
            # Ambil on-demand price dari pricing dict jika tersedia
            ec2_pricing = pricing.get('ec2_ondemand', {})
            current_price = ec2_pricing.get(inst_type, 0)
            if current_price > 0:
                estimated_savings_usd = round(current_price * _HOURS_PER_MONTH * (savings_pct / 100), 2)
        except Exception:
            pass

        name = inst.get('name') or inst['id']
        findings.append({
            'rule':                   'graviton_eligible',
            'category':               'Graviton Migration Opportunity',
            'resource_id':            inst['id'],
            'details':                f"{name}  ·  {inst_type} → {graviton_target}  ·  "
                                      f"{inst.get('platform', 'Linux')}  ·  est. savings {savings_pct}%",
            'estimated_monthly_cost': estimated_savings_usd,
            'severity':               'medium',
            'action':                 'Validasi kompatibilitas aplikasi sebelum migrasi ke Graviton',
        })


# ─── Rule 6: Public IPv4 Cost ─────────────────────────────────────────────────

_PUBLIC_IPV4_MONTHLY = 3.60  # $0.005/hr × 24 × 30 = $3.60/bulan


def _rule_public_ipv4_cost(assessment_data: dict, findings: list, pricing: dict):
    """Flag instance yang punya Public IPv4 (charged sejak Feb 2024)."""
    ec2_services = assessment_data.get('services', {}).get('ec2', {})
    instances = ec2_services.get('instances', [])

    for inst in instances:
        public_ip = inst.get('public_ip')
        if public_ip is None:
            continue

        name = inst.get('name') or inst['id']
        findings.append({
            'rule':                   'public_ipv4_cost',
            'category':               'Public IPv4 Cost',
            'resource_id':            inst['id'],
            'details':                f"{name}  ·  IP: {public_ip}  ·  {inst.get('type', '')}",
            'estimated_monthly_cost': _PUBLIC_IPV4_MONTHLY,
            'severity':               'low',
            'action':                 'Review apakah instance perlu public IP atau bisa pakai private + LB',
        })


# ─── Rule 7: S3 No Lifecycle ─────────────────────────────────────────────────

def _rule_s3_no_lifecycle(assessment_data: dict, findings: list, pricing: dict):
    """Flag S3 buckets yang tidak punya lifecycle rule."""
    buckets = assessment_data.get('services', {}).get('s3', {}).get('buckets', [])
    for bucket in buckets:
        if bucket.get('has_lifecycle') is None:
            continue
        if bucket.get('has_lifecycle') == False:
            findings.append({
                'rule':                   's3_no_lifecycle',
                'category':               'S3 Missing Lifecycle Policy',
                'resource_id':            bucket['name'],
                'details':                f"{bucket['name']}  ·  Tidak ada lifecycle rule  ·  versioning: {bucket.get('versioning_status', 'Unknown')}",
                'estimated_monthly_cost': 0,
                'severity':               'medium',
                'action':                 'Tambahkan lifecycle rule: transisi ke S3-IA setelah 30 hari, Glacier setelah 90 hari',
            })


# ─── Rule 8: S3 Versioning Without Expiry ────────────────────────────────────

def _rule_s3_versioning_no_expiry(assessment_data: dict, findings: list, pricing: dict):
    """Flag S3 buckets dengan versioning aktif tapi tanpa lifecycle/expiry rule."""
    buckets = assessment_data.get('services', {}).get('s3', {}).get('buckets', [])
    for bucket in buckets:
        if bucket.get('versioning_status') == 'Enabled' and bucket.get('has_lifecycle') == False:
            findings.append({
                'rule':                   's3_versioning_no_expiry',
                'category':               'S3 Versioning Without Expiry',
                'resource_id':            bucket['name'],
                'details':                f"{bucket['name']}  ·  Versioning aktif tanpa expiry rule  ·  storage bisa 2-5x lebih besar dari yang terlihat",
                'estimated_monthly_cost': 0,
                'severity':               'high',
                'action':                 'Tambahkan NoncurrentVersionExpiration rule. Rekomendasi: hapus noncurrent version setelah 30-90 hari',
            })


# ─── Entry Point ──────────────────────────────────────────────────────────────

def run_cost_optimization(session, assessment_data: dict):
    """
    Jalankan semua rule dan simpan hasilnya ke assessment_data['cost_optimization'].
    Pricing di-resolve dari utils.pricing (API → cache → tabel → fallback).
    """
    print("\n💰 Mendeteksi cost optimization opportunities...")

    region = assessment_data.get('region', 'us-east-1')

    # Resolve pricing (coba API, fallback cache/tabel)
    print(f"  ↻ Resolving harga untuk region {region}...")
    pricing, source = resolve_pricing(session, region)

    is_fallback = source.startswith("fallback_table_")
    is_api = source.startswith("pricing_api(")

    if is_fallback:
        print(f"  ⚠ Pricing fallback ke us-east-1 (region '{region}' belum tersedia)")
        price_note = (f"Region '{region}' belum tersedia. "
                      f"Estimasi memakai harga us-east-1 sebagai fallback.")
    elif is_api:
        components = source.split("(")[1].split(")")[0]
        print(f"  ✓ Pricing dari AWS Pricing API ({components}) — region {region}")
        price_note = (f"Harga region {region} dari AWS Price List Query API ({components}). "
                      f"Komponen lain dari tabel internal.")
    else:
        print(f"  ℹ Pricing dari tabel internal — region {region}")
        price_note = (f"Harga dari tabel internal untuk region {region}. "
                      f"Tambahkan IAM permission pricing:GetProducts untuk data real-time.")

    # Jalankan rules
    findings = []
    _rule_ebs_unattached(assessment_data, findings, pricing)
    _rule_ec2_stopped_ebs(assessment_data, findings, pricing)
    _rule_eip_idle(session, findings, pricing)
    _rule_lb_no_target(session, assessment_data, findings, pricing)
    _rule_graviton_eligible(assessment_data, findings, pricing)
    _rule_public_ipv4_cost(assessment_data, findings, pricing)
    _rule_s3_no_lifecycle(assessment_data, findings, pricing)
    _rule_s3_versioning_no_expiry(assessment_data, findings, pricing)

    # Summary
    summary = {}
    for f in findings:
        cat = f['category']
        if cat not in summary:
            summary[cat] = {'count': 0, 'savings': 0.0}
        summary[cat]['count'] += 1
        summary[cat]['savings'] += f['estimated_monthly_cost']

    total_savings = round(sum(f['estimated_monthly_cost'] for f in findings), 2)

    assessment_data['cost_optimization'] = {
        'total_potential_savings': total_savings,
        'findings':               findings,
        'summary':                summary,
        'price_region':           region,
        'price_source':           source,
        'price_region_fallback':  is_fallback,
        'price_region_note':      price_note,
    }

    if findings:
        print(f"✓ {len(findings)} findings — estimasi penghematan: ${total_savings:.2f}/bulan")
    else:
        print("✓ Tidak ditemukan waste yang jelas")

    return findings
