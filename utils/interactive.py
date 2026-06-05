"""
Interactive setup wizard untuk AWS Assessment Tool.
Menyediakan UI terminal yang interaktif untuk konfigurasi assessment.

Dependensi: questionary (pip install questionary)
Fallback   : kalau questionary tidak ada, kembalikan None dan main() akan
             jatuh ke mode .env + services.md seperti sebelumnya.
"""

import os
from dotenv import load_dotenv

try:
    import questionary
    from questionary import Choice, Separator
    QUESTIONARY_AVAILABLE = True
except ImportError:
    QUESTIONARY_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
# Definisi semua service yang tersedia, dikelompokkan per kategori.
# Format tiap item: (display_name, service_code, checked_by_default)
# checked_by_default hanya dipakai kalau service tidak ada di services.md.
# ─────────────────────────────────────────────────────────────────────────────
SERVICE_GROUPS = [
    ("── Compute ──────────────────────────────────", [
        ("EC2 (Elastic Compute Cloud)",        "ec2",          True),
        ("Lambda",                             "lambda",       False),
        ("EKS (Elastic Kubernetes Service)",   "eks",          False),
        ("ECR (Elastic Container Registry)",   "ecr",          False),
        ("ALB (Application Load Balancer)",    "alb",          True),
        ("NLB (Network Load Balancer)",        "nlb",          False),
    ]),
    ("── Storage ──────────────────────────────────", [
        ("S3 (Simple Storage Service)",        "s3",           True),
        ("EBS (Elastic Block Store)",          "ebs",          True),
        ("EFS (Elastic File System)",          "efs",          False),
        ("AWS Backup",                         "backup",       False),
    ]),
    ("── Database ─────────────────────────────────", [
        ("RDS (Relational Database Service)",  "rds",          True),
        ("DynamoDB",                           "dynamodb",     False),
        ("ElastiCache",                        "elasticache",  False),
    ]),
    ("── Networking ───────────────────────────────", [
        ("VPC (Virtual Private Cloud)",        "vpc",          True),
        ("NAT Gateway",                        "nat_gateway",  True),
        ("CloudFront",                         "cloudfront",   False),
        ("Route 53",                           "route53",      True),
    ]),
    ("── Security ─────────────────────────────────", [
        ("KMS (Key Management Service)",       "kms",          True),
        ("Secrets Manager",                    "secretsmanager", True),
        ("WAF (Web Application Firewall)",     "waf",          False),
    ]),
    ("── Operations ───────────────────────────────", [
        ("CloudWatch",                         "cloudwatch",   True),
        ("CloudTrail",                         "cloudtrail",   True),
        ("AWS Config",                         "config",       True),
    ]),
    ("── Integration & Analytics ──────────────────", [
        ("SNS (Simple Notification Service)",  "sns",          False),
        ("MSK (Managed Kafka)",                "msk",          False),
        ("Amazon MQ",                          "amazonmq",     False),
        ("AWS Glue",                           "glue",         False),
    ]),
]


def _mask(value: str, show_chars: int = 4) -> str:
    """Tampilkan N karakter pertama, sisanya bintang."""
    if not value:
        return ""
    if len(value) <= show_chars:
        return "*" * len(value)
    return value[:show_chars] + "*" * (len(value) - show_chars)


def _build_choices(defaults_from_md: dict) -> list:
    """
    Bangun list Choice + Separator untuk questionary.checkbox.
    State [x]/[ ] diambil dari services.md kalau ada,
    fallback ke checked_by_default di SERVICE_GROUPS.
    """
    choices = []
    for separator_label, services in SERVICE_GROUPS:
        choices.append(Separator(separator_label))
        for display_name, code, hardcoded_default in services:
            if code in defaults_from_md:
                checked = defaults_from_md[code].get('enabled', hardcoded_default)
            else:
                checked = hardcoded_default
            choices.append(Choice(
                title=display_name,
                value=code,
                checked=checked,
            ))
    return choices


def _prompt_credentials() -> tuple[str | None, str | None]:
    """Minta Access Key dan Secret Key secara manual di terminal."""
    access_key = questionary.text(
        "AWS Access Key ID:",
        validate=lambda x: True if x.strip() else "Access Key tidak boleh kosong",
    ).ask()
    if access_key is None:
        return None, None
    access_key = access_key.strip()

    secret_key = questionary.password(
        "AWS Secret Access Key:",
        validate=lambda x: True if x.strip() else "Secret Key tidak boleh kosong",
    ).ask()
    if secret_key is None:
        return None, None

    return access_key, secret_key


def run_interactive_setup(services_md_path: str = 'services.md') -> dict | None:
    """
    Jalankan interactive setup wizard di terminal.

    Return dict:
        {
            'customer_name'    : str,
            'region'           : str,
            'access_key'       : str,
            'secret_key'       : str,
            'selected_services': list[str],   # list service codes
        }
    Return None kalau user cancel (Ctrl+C) atau questionary tidak tersedia.
    """
    if not QUESTIONARY_AVAILABLE:
        print("⚠  Library 'questionary' tidak ditemukan.")
        print("   Install: pip install questionary")
        print("   Fallback ke mode .env + services.md\n")
        return None

    # Muat .env untuk nilai default
    load_dotenv()
    env_access_key    = os.getenv('AWS_ACCESS_KEY_ID', '')
    env_secret_key    = os.getenv('AWS_SECRET_ACCESS_KEY', '')
    env_region        = os.getenv('AWS_REGION', 'ap-southeast-1')
    env_customer_name = os.getenv('CUSTOMER_NAME', '')

    # ── Banner ────────────────────────────────────────────────────────────────
    print("\n" + "═" * 58)
    print("   🔍  AWS Account Assessment Tool  v2.0")
    print("═" * 58 + "\n")

    # ── 1. Nama Customer ──────────────────────────────────────────────────────
    customer_name = questionary.text(
        "Nama Customer:",
        default=env_customer_name or "",
        validate=lambda x: True if x.strip() else "Nama customer tidak boleh kosong",
    ).ask()
    if customer_name is None:
        return None
    customer_name = customer_name.strip()

    # ── 2. Region ─────────────────────────────────────────────────────────────
    region = questionary.text(
        "AWS Region:",
        default=env_region,
    ).ask()
    if region is None:
        return None
    region = region.strip() or env_region

    # ── 3. Credentials ────────────────────────────────────────────────────────
    print()
    if env_access_key and env_secret_key:
        print(f"  🔑 Credentials ditemukan di .env:")
        print(f"     AWS_ACCESS_KEY_ID     : {_mask(env_access_key)}")
        print(f"     AWS_SECRET_ACCESS_KEY : {_mask(env_secret_key)}\n")

        use_env = questionary.confirm(
            "Gunakan credentials dari .env?",
            default=True,
        ).ask()
        if use_env is None:
            return None

        if use_env:
            access_key, secret_key = env_access_key, env_secret_key
        else:
            print()
            access_key, secret_key = _prompt_credentials()
            if access_key is None:
                return None
    else:
        print("  ⚠  Credentials tidak ditemukan di .env, masukkan manual:\n")
        access_key, secret_key = _prompt_credentials()
        if access_key is None:
            return None

    # ── 4. Pilih Services ─────────────────────────────────────────────────────
    print()

    # Muat state [x]/[ ] dari services.md sebagai default
    try:
        from utils.config_loader import load_services_config
        # Suppress print dari config_loader saat load defaults
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            md_defaults = load_services_config(services_md_path)
    except Exception:
        md_defaults = {}

    choices = _build_choices(md_defaults)

    selected = questionary.checkbox(
        "Pilih Services yang ingin di-assessment:\n"
        "  ↑↓ navigasi   ·   Spasi toggle   ·   a select-all   ·   Enter submit\n",
        choices=choices,
        validate=lambda x: True if x else "Pilih minimal 1 service",
    ).ask()

    if not selected:
        return None

    # ── 5. Konfirmasi ─────────────────────────────────────────────────────────
    print(f"\n  ┌─ Ringkasan Assessment ──────────────────────┐")
    print(f"  │  Customer : {customer_name:<34} │")
    print(f"  │  Region   : {region:<34} │")
    print(f"  │  Services : {str(len(selected)) + ' dipilih':<34} │")
    print(f"  └─────────────────────────────────────────────┘\n")

    confirmed = questionary.confirm("Mulai assessment?", default=True).ask()
    if not confirmed:
        print("\n  Assessment dibatalkan.\n")
        return None

    print()
    return {
        'customer_name':     customer_name,
        'region':            region,
        'access_key':        access_key,
        'secret_key':        secret_key,
        'selected_services': selected,
    }
