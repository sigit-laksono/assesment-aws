"""
AWS Pricing Data Provider
==========================
Modul independen untuk mengambil dan menyediakan data harga AWS.
Bisa dipanggil dari cost_optimization, scheduler, atau script CLI lainnya.

Strategi resolusi (4 lapis, prioritas atas ke bawah):
  1. AWS Price List Query API (real-time via boto3, gratis)
  2. File cache di `data-pricing/extracted/<region>.json`
  3. Tabel internal `_REGION_PRICING` (estimasi region populer)
  4. Fallback us-east-1 + flag warning

Public API:
  - fetch_pricing(session, region) → tarik dari API, simpan ke cache
  - get_pricing(region)            → resolve dari cache/tabel (tanpa API call)
  - resolve_pricing(session, region) → fetch dulu, fallback ke cache/tabel
"""
import json
from pathlib import Path
from datetime import datetime, timezone

_EXTRACTED_DIR = Path(__file__).resolve().parent.parent / "data-pricing" / "extracted"

# Endpoint Query API hanya tersedia di 3 region ini
_PRICING_API_REGIONS = ['us-east-1', 'ap-south-1', 'eu-central-1']

_HOURS_PER_MONTH = 730

# ─── Tabel harga estimasi per region (USD) ────────────────────────────────────
# Fallback kalau API dan cache tidak tersedia.

_REGION_PRICING = {
    'us-east-1':      {'ebs': {'gp2': 0.10,  'gp3': 0.08,   'io1': 0.125, 'io2': 0.125, 'st1': 0.045, 'sc1': 0.015,  'standard': 0.05},  'eip_hr': 0.005, 'alb_hr': 0.0225, 'nlb_hr': 0.0225},
    'us-east-2':      {'ebs': {'gp2': 0.10,  'gp3': 0.08,   'io1': 0.125, 'io2': 0.125, 'st1': 0.045, 'sc1': 0.015,  'standard': 0.05},  'eip_hr': 0.005, 'alb_hr': 0.0225, 'nlb_hr': 0.0225},
    'us-west-1':      {'ebs': {'gp2': 0.12,  'gp3': 0.096,  'io1': 0.138, 'io2': 0.138, 'st1': 0.054, 'sc1': 0.018,  'standard': 0.08},  'eip_hr': 0.005, 'alb_hr': 0.0252, 'nlb_hr': 0.0252},
    'us-west-2':      {'ebs': {'gp2': 0.10,  'gp3': 0.08,   'io1': 0.125, 'io2': 0.125, 'st1': 0.045, 'sc1': 0.015,  'standard': 0.05},  'eip_hr': 0.005, 'alb_hr': 0.0225, 'nlb_hr': 0.0225},
    'ap-southeast-1': {'ebs': {'gp2': 0.12,  'gp3': 0.0928, 'io1': 0.138, 'io2': 0.138, 'st1': 0.054, 'sc1': 0.0174, 'standard': 0.08},  'eip_hr': 0.005, 'alb_hr': 0.0305, 'nlb_hr': 0.0225},
    'ap-southeast-2': {'ebs': {'gp2': 0.12,  'gp3': 0.096,  'io1': 0.138, 'io2': 0.138, 'st1': 0.054, 'sc1': 0.018,  'standard': 0.08},  'eip_hr': 0.005, 'alb_hr': 0.0305, 'nlb_hr': 0.0225},
    'ap-southeast-3': {'ebs': {'gp2': 0.121, 'gp3': 0.0968, 'io1': 0.138, 'io2': 0.138, 'st1': 0.054, 'sc1': 0.018,  'standard': 0.08},  'eip_hr': 0.005, 'alb_hr': 0.0305, 'nlb_hr': 0.0225},
    'ap-northeast-1': {'ebs': {'gp2': 0.12,  'gp3': 0.096,  'io1': 0.142, 'io2': 0.142, 'st1': 0.054, 'sc1': 0.018,  'standard': 0.08},  'eip_hr': 0.005, 'alb_hr': 0.0314, 'nlb_hr': 0.0243},
    'ap-northeast-2': {'ebs': {'gp2': 0.114, 'gp3': 0.0912, 'io1': 0.1278,'io2': 0.1278,'st1': 0.051, 'sc1': 0.017,  'standard': 0.08},  'eip_hr': 0.005, 'alb_hr': 0.03,   'nlb_hr': 0.0225},
    'ap-south-1':     {'ebs': {'gp2': 0.114, 'gp3': 0.0912, 'io1': 0.131, 'io2': 0.131, 'st1': 0.051, 'sc1': 0.017,  'standard': 0.08},  'eip_hr': 0.005, 'alb_hr': 0.027,  'nlb_hr': 0.0225},
    'eu-west-1':      {'ebs': {'gp2': 0.11,  'gp3': 0.0928, 'io1': 0.138, 'io2': 0.138, 'st1': 0.05,  'sc1': 0.0168, 'standard': 0.055}, 'eip_hr': 0.005, 'alb_hr': 0.0252, 'nlb_hr': 0.0225},
    'eu-west-2':      {'ebs': {'gp2': 0.116, 'gp3': 0.0928, 'io1': 0.145, 'io2': 0.145, 'st1': 0.052, 'sc1': 0.0174, 'standard': 0.058}, 'eip_hr': 0.005, 'alb_hr': 0.0264, 'nlb_hr': 0.0234},
    'eu-central-1':   {'ebs': {'gp2': 0.119, 'gp3': 0.0952, 'io1': 0.149, 'io2': 0.149, 'st1': 0.054, 'sc1': 0.018,  'standard': 0.059}, 'eip_hr': 0.005, 'alb_hr': 0.027,  'nlb_hr': 0.0243},
}

_DEFAULT_REGION = 'us-east-1'
_EBS_VOLUME_TYPES = ['gp2', 'gp3', 'io1', 'io2', 'st1', 'sc1', 'standard']

# ─── EC2 on-demand base prices (us-east-1, Linux, On-Demand, USD/hr) ──────────
# Covers families eligible for Graviton migration (m5/m5a/c5/c5a/r5/r5a/t3/t3a).
# Other regions scale via _EC2_REGION_MULTIPLIER.
_EC2_BASE_PRICES = {
    # t3
    't3.nano':    0.0052, 't3.micro':   0.0104, 't3.small':   0.0208,
    't3.medium':  0.0416, 't3.large':   0.0832, 't3.xlarge':  0.1664,
    't3.2xlarge': 0.3328,
    # t3a
    't3a.nano':    0.0047, 't3a.micro':   0.0094, 't3a.small':   0.0188,
    't3a.medium':  0.0376, 't3a.large':   0.0752, 't3a.xlarge':  0.1504,
    't3a.2xlarge': 0.3008,
    # m5
    'm5.large':    0.096,  'm5.xlarge':   0.192,  'm5.2xlarge':  0.384,
    'm5.4xlarge':  0.768,  'm5.8xlarge':  1.536,  'm5.12xlarge': 2.304,
    'm5.16xlarge': 3.072,  'm5.24xlarge': 4.608,
    # m5a
    'm5a.large':    0.086,  'm5a.xlarge':   0.172,  'm5a.2xlarge':  0.344,
    'm5a.4xlarge':  0.688,  'm5a.8xlarge':  1.376,  'm5a.12xlarge': 2.064,
    'm5a.16xlarge': 2.752,  'm5a.24xlarge': 4.128,
    # c5
    'c5.large':    0.085,  'c5.xlarge':   0.170,  'c5.2xlarge':  0.340,
    'c5.4xlarge':  0.680,  'c5.9xlarge':  1.530,  'c5.12xlarge': 2.040,
    'c5.18xlarge': 3.060,  'c5.24xlarge': 4.080,
    # c5a
    'c5a.large':    0.077,  'c5a.xlarge':   0.154,  'c5a.2xlarge':  0.308,
    'c5a.4xlarge':  0.616,  'c5a.8xlarge':  1.232,  'c5a.12xlarge': 1.848,
    'c5a.16xlarge': 2.464,  'c5a.24xlarge': 3.696,
    # r5
    'r5.large':    0.126,  'r5.xlarge':   0.252,  'r5.2xlarge':  0.504,
    'r5.4xlarge':  1.008,  'r5.8xlarge':  2.016,  'r5.12xlarge': 3.024,
    'r5.16xlarge': 4.032,  'r5.24xlarge': 6.048,
    # r5a
    'r5a.large':    0.113,  'r5a.xlarge':   0.226,  'r5a.2xlarge':  0.452,
    'r5a.4xlarge':  0.904,  'r5a.8xlarge':  1.808,  'r5a.12xlarge': 2.712,
    'r5a.16xlarge': 3.616,  'r5a.24xlarge': 5.424,
}

# Multiplier relatif terhadap us-east-1 untuk estimasi harga EC2 per region
_EC2_REGION_MULTIPLIER = {
    'us-east-1':      1.00, 'us-east-2':      1.00,
    'us-west-1':      1.14, 'us-west-2':      1.00,
    'ap-southeast-1': 1.23, 'ap-southeast-2': 1.23, 'ap-southeast-3': 1.24,
    'ap-northeast-1': 1.26, 'ap-northeast-2': 1.18, 'ap-northeast-3': 1.28,
    'ap-south-1':     1.17, 'ap-south-2':     1.20,
    'eu-west-1':      1.11, 'eu-west-2':      1.16, 'eu-west-3':      1.16,
    'eu-central-1':   1.14, 'eu-central-2':   1.18,
    'eu-north-1':     1.10, 'eu-south-1':     1.20,
    'sa-east-1':      1.46, 'ca-central-1':   1.06,
    'me-south-1':     1.30, 'af-south-1':     1.35,
}

# Mapping region → usagetype prefix (AWS naming convention)
_REGION_PREFIX_MAP = {
    'us-east-1': 'USE1', 'us-east-2': 'USE2', 'us-west-1': 'USW1', 'us-west-2': 'USW2',
    'ap-southeast-1': 'APS1', 'ap-southeast-2': 'APS2', 'ap-southeast-3': 'APS4',
    'ap-northeast-1': 'APN1', 'ap-northeast-2': 'APN2', 'ap-northeast-3': 'APN3',
    'ap-south-1': 'APS3', 'ap-south-2': 'APS5',
    'eu-west-1': 'EUW1', 'eu-west-2': 'EUW2', 'eu-west-3': 'EUW3',
    'eu-central-1': 'EUC1', 'eu-central-2': 'EUC2',
    'eu-north-1': 'EUN1', 'eu-south-1': 'EUS1',
    'sa-east-1': 'SAE1', 'ca-central-1': 'CAN1',
    'me-south-1': 'MES1', 'me-central-1': 'MEC1',
    'af-south-1': 'AFS1', 'il-central-1': 'ILC1',
}


def _region_prefix(region: str) -> str:
    """Convert region code ke usagetype prefix."""
    return _REGION_PREFIX_MAP.get(region, region.upper().replace('-', ''))


# ─── Fetch dari AWS Price List Query API ──────────────────────────────────────

def fetch_pricing(session, region: str) -> dict | None:
    """
    Tarik data harga real-time dari AWS Price List Query API.
    Hasilnya langsung di-cache ke file extracted.

    Args:
        session: boto3.Session (harus punya IAM permission pricing:GetProducts)
        region:  AWS region code target (mis. 'ap-southeast-3')

    Returns:
        dict dengan keys: ebs, eip_hr, alb_hr, nlb_hr — atau None kalau gagal total.
    """
    try:
        pricing_client = session.client('pricing', region_name=_PRICING_API_REGIONS[0])
    except Exception:
        return None

    result = {}

    # ── EBS pricing (AmazonEC2 / Storage) ──
    ebs = {}
    for vol_type in _EBS_VOLUME_TYPES:
        try:
            resp = pricing_client.get_products(
                ServiceCode='AmazonEC2',
                Filters=[
                    {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'Storage'},
                    {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': region},
                    {'Type': 'TERM_MATCH', 'Field': 'volumeApiName', 'Value': vol_type},
                ],
                MaxResults=1,
            )
            for item_str in resp.get('PriceList', []):
                item = json.loads(item_str)
                for term in item.get('terms', {}).get('OnDemand', {}).values():
                    for pd in term.get('priceDimensions', {}).values():
                        usd = pd.get('pricePerUnit', {}).get('USD')
                        if usd:
                            ebs[vol_type] = round(float(usd), 6)
        except Exception:
            pass

    if ebs:
        result['ebs'] = ebs

    # ── Elastic IP pricing (AmazonVPC) ──
    try:
        resp = pricing_client.get_products(
            ServiceCode='AmazonVPC',
            Filters=[
                {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'IP Address'},
                {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': region},
            ],
            MaxResults=10,
        )
        for item_str in resp.get('PriceList', []):
            item = json.loads(item_str)
            usage = (item.get('product', {}).get('attributes', {}).get('usagetype', '') or '').lower()
            if 'idleaddress' in usage:
                for term in item.get('terms', {}).get('OnDemand', {}).values():
                    for pd in term.get('priceDimensions', {}).values():
                        usd = pd.get('pricePerUnit', {}).get('USD')
                        if usd and float(usd) > 0:
                            result['eip_hr'] = round(float(usd), 6)
    except Exception:
        pass

    # ── ALB pricing (AWSELB) ──
    try:
        resp = pricing_client.get_products(
            ServiceCode='AWSELB',
            Filters=[
                {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'Load Balancer-Application'},
                {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': region},
                {'Type': 'TERM_MATCH', 'Field': 'usagetype', 'Value': f'{_region_prefix(region)}-LoadBalancerUsage'},
            ],
            MaxResults=1,
        )
        for item_str in resp.get('PriceList', []):
            item = json.loads(item_str)
            for term in item.get('terms', {}).get('OnDemand', {}).values():
                for pd in term.get('priceDimensions', {}).values():
                    usd = pd.get('pricePerUnit', {}).get('USD')
                    if usd and float(usd) > 0:
                        result['alb_hr'] = round(float(usd), 6)
    except Exception:
        pass

    # ── NLB pricing (AWSELB) ──
    try:
        resp = pricing_client.get_products(
            ServiceCode='AWSELB',
            Filters=[
                {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'Load Balancer-Network'},
                {'Type': 'TERM_MATCH', 'Field': 'regionCode', 'Value': region},
                {'Type': 'TERM_MATCH', 'Field': 'usagetype', 'Value': f'{_region_prefix(region)}-LoadBalancerUsage'},
            ],
            MaxResults=1,
        )
        for item_str in resp.get('PriceList', []):
            item = json.loads(item_str)
            for term in item.get('terms', {}).get('OnDemand', {}).values():
                for pd in term.get('priceDimensions', {}).values():
                    usd = pd.get('pricePerUnit', {}).get('USD')
                    if usd and float(usd) > 0:
                        result['nlb_hr'] = round(float(usd), 6)
    except Exception:
        pass

    if not result:
        return None

    # Auto-cache ke file extracted
    _save_to_cache(region, result)
    return result


# ─── Cache management ─────────────────────────────────────────────────────────

def _save_to_cache(region: str, data: dict):
    """Simpan pricing data ke file cache."""
    _EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    out_file = _EXTRACTED_DIR / f"{region}.json"

    existing = {}
    if out_file.exists():
        try:
            with open(out_file, encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    existing.setdefault("region", region)
    if 'ebs' in data:
        existing.setdefault('ebs', {}).update(data['ebs'])
    for key in ('eip_hr', 'alb_hr', 'nlb_hr'):
        if key in data and data[key] is not None:
            existing[key] = data[key]

    existing['last_api_fetch'] = datetime.now(timezone.utc).isoformat()

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, sort_keys=True)


def _load_cache(region: str) -> dict | None:
    """Load file cache untuk region. Return None kalau tidak ada."""
    path = _EXTRACTED_DIR / f"{region}.json"
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


# ─── Resolve pricing (merge cache + tabel) ────────────────────────────────────

def get_pricing(region: str) -> tuple[dict, str]:
    """
    Resolve pricing TANPA API call — hanya dari cache dan tabel.
    Cocok untuk mode offline / scheduler sudah jalan duluan.

    Returns:
        (pricing_dict, source_label)
        pricing_dict keys: ebs (dict), eip_hr, alb_hr, nlb_hr
    """
    cached = _load_cache(region)
    return _merge(cached, region)


def resolve_pricing(session, region: str) -> tuple[dict, str]:
    """
    Resolve pricing LENGKAP — coba API dulu, fallback ke cache/tabel.
    Ini yang dipanggil oleh cost_optimization saat assessment.

    Returns:
        (pricing_dict, source_label)
    """
    # Coba fetch real-time
    api_data = None
    try:
        api_data = fetch_pricing(session, region)
    except Exception:
        pass

    # Load cache (termasuk data yang baru saja di-cache oleh fetch_pricing)
    cached = _load_cache(region)
    return _merge(cached, region)


def _merge(cached: dict | None, region: str) -> tuple[dict, str]:
    """Merge cached data dengan tabel internal. Returns (pricing_dict, source_label)."""
    table = _REGION_PRICING.get(region) or _REGION_PRICING[_DEFAULT_REGION]
    table_is_fallback = region not in _REGION_PRICING

    # EC2 on-demand selalu dihitung — tersedia di semua path
    multiplier = _EC2_REGION_MULTIPLIER.get(region, 1.15)
    ec2_ondemand = {
        inst: round(price * multiplier, 6)
        for inst, price in _EC2_BASE_PRICES.items()
    }

    if not cached:
        result = dict(table)
        result['ec2_ondemand'] = ec2_ondemand
        if table_is_fallback:
            return result, f"fallback_table_{_DEFAULT_REGION}"
        return result, f"internal_table_{region}"

    # Base dari tabel, override dari cache
    merged = {
        'ebs':          dict(table['ebs']),
        'eip_hr':       table['eip_hr'],
        'alb_hr':       table['alb_hr'],
        'nlb_hr':       table['nlb_hr'],
        'ec2_ondemand': ec2_ondemand,
    }
    sources = []

    if 'ebs' in cached:
        merged['ebs'].update(cached['ebs'])
        sources.append('EBS')
    for key, label in [('eip_hr', 'EIP'), ('alb_hr', 'ALB'), ('nlb_hr', 'NLB')]:
        if key in cached and cached[key] is not None:
            merged[key] = cached[key]
            sources.append(label)

    if sources:
        return merged, f"pricing_api({'+'.join(sources)})_{region}"

    if table_is_fallback:
        return merged, f"fallback_table_{_DEFAULT_REGION}"
    return merged, f"internal_table_{region}"


# ─── Utility ──────────────────────────────────────────────────────────────────

def get_cache_info(region: str) -> dict | None:
    """Metadata tentang cache: kapan terakhir fetch, komponen apa saja."""
    cached = _load_cache(region)
    if not cached:
        return None
    return {
        'region': region,
        'last_api_fetch': cached.get('last_api_fetch'),
        'has_ebs': 'ebs' in cached,
        'has_eip': 'eip_hr' in cached,
        'has_alb': 'alb_hr' in cached,
        'has_nlb': 'nlb_hr' in cached,
    }
