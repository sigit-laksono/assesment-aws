"""
Cost Optimization Collector
============================
Mendeteksi resource yang jelas-jelas terbuang (waste) — bukan right-sizing.
Scope: 4 rule dengan confidence tinggi (tidak ada false-positive):

  1. EBS Unattached        — volume state 'available', tidak dipakai siapapun
  2. EC2 Stopped + EBS     — instance mati tapi disk-nya masih dibayar
  3. Elastic IP Idle       — EIP tidak ter-assign ke resource manapun
  4. LB Tanpa Target       — ALB/NLB tidak punya target aktif, bayar fixed cost sia-sia

Harga adalah estimasi berdasarkan region ap-southeast-1.
Untuk region lain hasilnya tetap relevan sebagai indikasi arah, bukan angka pasti.
"""

# ─── Harga estimasi (ap-southeast-1, USD/bulan) ───────────────────────────────

_EBS_PRICE_PER_GB = {
    'gp2':      0.10,
    'gp3':      0.08,
    'io1':      0.125,
    'io2':      0.125,
    'st1':      0.045,
    'sc1':      0.025,
    'standard': 0.05,
}
_EBS_DEFAULT_PRICE = 0.10   # fallback kalau type tidak dikenali

_EIP_PRICE_PER_MONTH  = round(0.005 * 24 * 30, 2)   # $3.60
_ALB_PRICE_PER_MONTH  = 22.27
_NLB_PRICE_PER_MONTH  = 16.43


def _ebs_monthly_cost(size_gb: int, vol_type: str) -> float:
    price = _EBS_PRICE_PER_GB.get(vol_type, _EBS_DEFAULT_PRICE)
    return round(size_gb * price, 2)


# ─── Rule 1: EBS Unattached ───────────────────────────────────────────────────

def _rule_ebs_unattached(assessment_data: dict, findings: list):
    ebs = assessment_data.get('services', {}).get('ebs', {})
    for vol in ebs.get('volumes', []):
        if vol.get('state') == 'available':
            cost = _ebs_monthly_cost(vol.get('size', 0), vol.get('type', ''))
            findings.append({
                'rule':                   'ebs_unattached',
                'category':               'EBS Unattached',
                'resource_id':            vol['id'],
                'details':                f"{vol.get('size')} GB  ·  {vol.get('type')}  ·  "
                                          f"{'Encrypted' if vol.get('encrypted') else 'Not encrypted'}",
                'estimated_monthly_cost': cost,
            })


# ─── Rule 2: EC2 Stopped + EBS Attached ──────────────────────────────────────

def _rule_ec2_stopped_ebs(assessment_data: dict, findings: list):
    ec2_services = assessment_data.get('services', {}).get('ec2', {})
    ebs_services = assessment_data.get('services', {}).get('ebs', {})

    if not ec2_services or not ebs_services:
        return   # salah satu tidak di-collect, skip

    stopped_ids = {
        inst['id']
        for inst in ec2_services.get('instances', [])
        if inst.get('state') == 'stopped'
    }
    if not stopped_ids:
        return

    for vol in ebs_services.get('volumes', []):
        if vol.get('attached_instance') in stopped_ids:
            cost = _ebs_monthly_cost(vol.get('size', 0), vol.get('type', ''))
            findings.append({
                'rule':                   'ec2_stopped_ebs',
                'category':               'EC2 Stopped (EBS masih berjalan)',
                'resource_id':            vol['id'],
                'details':                f"Attached ke instance {vol['attached_instance']} (stopped)  ·  "
                                          f"{vol.get('size')} GB  ·  {vol.get('type')}",
                'estimated_monthly_cost': cost,
            })


# ─── Rule 3: Elastic IP Idle ──────────────────────────────────────────────────

def _rule_eip_idle(session, findings: list):
    try:
        ec2 = session.client('ec2')
        response = ec2.describe_addresses()
        for addr in response.get('Addresses', []):
            if not addr.get('AssociationId'):   # tidak ter-assign ke resource apapun
                findings.append({
                    'rule':                   'eip_idle',
                    'category':               'Elastic IP Idle',
                    'resource_id':            addr.get('AllocationId', addr.get('PublicIp', 'N/A')),
                    'details':                f"Public IP: {addr.get('PublicIp', 'N/A')}  ·  tidak ter-assign",
                    'estimated_monthly_cost': _EIP_PRICE_PER_MONTH,
                })
    except Exception as e:
        print(f"  ⚠ Tidak bisa cek Elastic IP: {e}")


# ─── Rule 4: Load Balancer Tanpa Target Aktif ─────────────────────────────────

def _rule_lb_no_target(session, assessment_data: dict, findings: list):
    """
    Flag ALB/NLB yang tidak punya target group sama sekali,
    atau semua target group-nya tidak punya target registered.
    """
    # Kumpulkan ARN + type dari ALB dan NLB yang sudah di-collect
    lbs = []
    for svc_key, lb_type, price in [
        ('alb', 'ALB', _ALB_PRICE_PER_MONTH),
        ('nlb', 'NLB', _NLB_PRICE_PER_MONTH),
    ]:
        for lb in assessment_data.get('services', {}).get(svc_key, {}).get('load_balancers', []):
            lbs.append({
                'arn':   lb['arn'],
                'name':  lb['name'],
                'type':  lb_type,
                'price': price,
            })

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
                    # Tidak ada target group sama sekali → pasti idle
                    findings.append({
                        'rule':                   'lb_no_target',
                        'category':               f"{lb['type']} Tanpa Target",
                        'resource_id':            lb['name'],
                        'details':                'Tidak memiliki target group',
                        'estimated_monthly_cost': lb['price'],
                    })
                    continue

                # Cek apakah ada target yang registered di salah satu TG
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
                    })

            except Exception as e:
                print(f"  ⚠ Tidak bisa cek target {lb['name']}: {e}")

    except Exception as e:
        print(f"  ⚠ Tidak bisa cek Load Balancer targets: {e}")


# ─── Entry Point ──────────────────────────────────────────────────────────────

def run_cost_optimization(session, assessment_data: dict):
    """
    Jalankan semua rule dan simpan hasilnya ke assessment_data['cost_optimization'].
    Selalu dipanggil setelah inventory loop selesai.
    """
    print("\n💰 Mendeteksi cost optimization opportunities...")

    findings = []
    _rule_ebs_unattached(assessment_data, findings)
    _rule_ec2_stopped_ebs(assessment_data, findings)
    _rule_eip_idle(session, findings)
    _rule_lb_no_target(session, assessment_data, findings)

    # Hitung summary per kategori
    summary = {}
    for f in findings:
        cat = f['category']
        if cat not in summary:
            summary[cat] = {'count': 0, 'savings': 0.0}
        summary[cat]['count']   += 1
        summary[cat]['savings'] += f['estimated_monthly_cost']

    total_savings = round(sum(f['estimated_monthly_cost'] for f in findings), 2)

    assessment_data['cost_optimization'] = {
        'total_potential_savings': total_savings,
        'findings':                findings,
        'summary':                 summary,
        'price_region_note':       'Estimasi harga berdasarkan ap-southeast-1. '
                                   'Region lain mungkin berbeda ±10–20%.',
    }

    if findings:
        print(f"✓ {len(findings)} findings — estimasi penghematan: ${total_savings:.2f}/bulan")
    else:
        print("✓ Tidak ditemukan waste yang jelas")

    return findings
