"""
Interactive setup wizard untuk AWS Assessment Tool.
Menggunakan input() standar Python — kompatibel dengan semua terminal
termasuk WSL, SSH, dan terminal tanpa dukungan ANSI penuh.
"""

import os
import getpass
from dotenv import load_dotenv


# ─────────────────────────────────────────────────────────────────────────────
# Definisi semua service yang tersedia, dikelompokkan per kategori.
# Format: (display_name, service_code, checked_by_default)
# ─────────────────────────────────────────────────────────────────────────────
SERVICE_GROUPS = [
    ("Compute", [
        ("EC2 (Elastic Compute Cloud)",        "ec2",           True),
        ("Lambda",                             "lambda",        False),
        ("EKS (Elastic Kubernetes Service)",   "eks",           False),
        ("ECR (Elastic Container Registry)",   "ecr",           False),
        ("ALB (Application Load Balancer)",    "alb",           True),
        ("NLB (Network Load Balancer)",        "nlb",           False),
    ]),
    ("Storage", [
        ("S3 (Simple Storage Service)",        "s3",            True),
        ("EBS (Elastic Block Store)",          "ebs",           True),
        ("EFS (Elastic File System)",          "efs",           False),
        ("AWS Backup",                         "backup",        False),
    ]),
    ("Database", [
        ("RDS (Relational Database Service)",  "rds",           True),
        ("DynamoDB",                           "dynamodb",      False),
        ("ElastiCache",                        "elasticache",   False),
    ]),
    ("Networking", [
        ("VPC (Virtual Private Cloud)",        "vpc",           True),
        ("NAT Gateway",                        "nat_gateway",   True),
        ("CloudFront",                         "cloudfront",    False),
        ("Route 53",                           "route53",       True),
    ]),
    ("Security", [
        ("KMS (Key Management Service)",       "kms",           True),
        ("Secrets Manager",                    "secretsmanager", True),
        ("WAF (Web Application Firewall)",     "waf",           False),
    ]),
    ("Operations", [
        ("CloudWatch",                         "cloudwatch",    True),
        ("CloudTrail",                         "cloudtrail",    True),
        ("AWS Config",                         "config",        True),
    ]),
    ("Integration & Analytics", [
        ("SNS (Simple Notification Service)",  "sns",           False),
        ("MSK (Managed Kafka)",                "msk",           False),
        ("Amazon MQ",                          "amazonmq",      False),
        ("AWS Glue",                           "glue",          False),
    ]),
]


def _mask(value: str, show_chars: int = 4) -> str:
    """Tampilkan N karakter pertama, sisanya bintang."""
    if not value:
        return ""
    if len(value) <= show_chars:
        return "*" * len(value)
    return value[:show_chars] + "*" * (len(value) - show_chars)


def _prompt(label: str, default: str = "") -> str:
    """Input satu baris dengan nilai default."""
    if default:
        val = input(f"  {label} [{default}]: ").strip()
        return val if val else default
    return input(f"  {label}: ").strip()


def _confirm(label: str, default: bool = True) -> bool:
    """Konfirmasi y/n dengan default."""
    hint = "Y/n" if default else "y/N"
    answer = input(f"  {label} ({hint}): ").strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")


def _build_service_table(md_defaults: dict) -> tuple[list, list]:
    """
    Bangun flat list semua service beserta default check-state.
    Return: (flat_services, default_indices)
      flat_services : list of (no, display_name, code)
      default_indices: list nomor (1-based) yang default dipilih
    """
    flat = []
    defaults = []
    no = 1

    for _, services in SERVICE_GROUPS:
        for display_name, code, hardcoded_default in services:
            # Prioritaskan state dari services.md kalau ada
            if code in md_defaults:
                checked = md_defaults[code].get('enabled', hardcoded_default)
            else:
                checked = hardcoded_default
            flat.append((no, display_name, code))
            if checked:
                defaults.append(no)
            no += 1

    return flat, defaults


def _print_service_table(flat_services: list, selected_nos: list):
    """Cetak tabel service dengan marker [x]/[ ]."""
    current_category_idx = 0
    category_boundaries = []  # (start_no, category_name)

    # Hitung batas per kategori
    no = 1
    for cat_name, services in SERVICE_GROUPS:
        category_boundaries.append((no, cat_name))
        no += len(services)

    cat_iter = iter(category_boundaries)
    next_cat_no, next_cat_name = next(cat_iter)

    for (no, display_name, code) in flat_services:
        # Cetak header kategori kalau sudah waktunya
        if no == next_cat_no:
            print(f"\n  ── {next_cat_name} {'─' * (30 - len(next_cat_name))}")
            try:
                next_cat_no, next_cat_name = next(cat_iter)
            except StopIteration:
                next_cat_no = 9999

        print(f"  {no:>2}.  {display_name}")


def run_interactive_setup(services_md_path: str = 'services.md') -> dict | None:
    """
    Jalankan interactive setup wizard di terminal.

    Return dict:
        {
            'customer_name'    : str,
            'region'           : str,
            'access_key'       : str,
            'secret_key'       : str,
            'selected_services': list[str],
        }
    Return None kalau user cancel.
    """
    # Muat .env untuk nilai default
    load_dotenv()
    env_access_key    = os.getenv('AWS_ACCESS_KEY_ID', '')
    env_secret_key    = os.getenv('AWS_SECRET_ACCESS_KEY', '')
    env_region        = os.getenv('AWS_REGION', 'ap-southeast-1')
    env_customer_name = os.getenv('CUSTOMER_NAME', '')

    # Muat defaults dari services.md
    try:
        from utils.config_loader import load_services_config
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            md_defaults = load_services_config(services_md_path)
    except Exception:
        md_defaults = {}

    flat_services, default_nos = _build_service_table(md_defaults)

    print("\n" + "=" * 58)
    print("   AWS Account Assessment Tool  v2.0")
    print("=" * 58)

    try:
        # ── 1. Customer Name ──────────────────────────────────────────────────
        print("\n[1/4] Informasi Customer")
        print("-" * 40)
        customer_name = _prompt("Nama Customer", env_customer_name)
        if not customer_name:
            print("  Nama customer tidak boleh kosong.")
            return None

        region = _prompt("AWS Region", env_region)

        # ── 2. Credentials ────────────────────────────────────────────────────
        print("\n[2/4] AWS Credentials")
        print("-" * 40)

        if env_access_key and env_secret_key:
            print(f"  Credentials ditemukan di .env:")
            print(f"    AWS_ACCESS_KEY_ID     : {_mask(env_access_key)}")
            print(f"    AWS_SECRET_ACCESS_KEY : {_mask(env_secret_key)}")
            print()
            use_env = _confirm("Gunakan credentials dari .env?", default=True)

            if use_env:
                access_key = env_access_key
                secret_key = env_secret_key
            else:
                access_key = _prompt("AWS Access Key ID")
                if not access_key:
                    return None
                secret_key = getpass.getpass("  AWS Secret Access Key: ").strip()
                if not secret_key:
                    return None
        else:
            print("  Credentials tidak ditemukan di .env, masukkan manual:")
            print()
            access_key = _prompt("AWS Access Key ID")
            if not access_key:
                return None
            secret_key = getpass.getpass("  AWS Secret Access Key: ").strip()
            if not secret_key:
                return None

        # ── 3. Service Selection ──────────────────────────────────────────────
        print("\n[3/4] Pilih Services")
        print("-" * 40)
        _print_service_table(flat_services, default_nos)

        total = len(flat_services)
        default_str = ",".join(str(n) for n in default_nos)
        print(f"\n  Masukkan nomor yang ingin di-scan, pisah dengan koma.")
        print(f"  Contoh: 1,3,7   |  'all' untuk semua  |  Enter untuk default")
        print()
        raw = input(f"  Pilihan [{default_str}]: ").strip()

        if not raw:
            # Enter = pakai default
            selected_nos = default_nos
        elif raw.lower() == 'all':
            selected_nos = list(range(1, total + 1))
        else:
            try:
                selected_nos = [int(x.strip()) for x in raw.split(',')
                                if x.strip().isdigit()]
                selected_nos = [n for n in selected_nos if 1 <= n <= total]
                if not selected_nos:
                    print("  Tidak ada nomor valid, pakai default.")
                    selected_nos = default_nos
            except ValueError:
                print("  Input tidak valid, pakai default.")
                selected_nos = default_nos

        # Tampilkan ulang pilihan yang terpilih
        selected_services = [
            code for (no, _, code) in flat_services if no in selected_nos
        ]

        # ── 4. Konfirmasi ─────────────────────────────────────────────────────
        print("\n[4/4] Konfirmasi")
        print("-" * 40)
        print(f"  Customer : {customer_name}")
        print(f"  Region   : {region}")
        print(f"  Services : {len(selected_services)} dipilih")
        print(f"             {', '.join(selected_services)}")
        print()

        if not _confirm("Mulai assessment?", default=True):
            print("\n  Assessment dibatalkan.\n")
            return None

        print()
        return {
            'customer_name':     customer_name,
            'region':            region,
            'access_key':        access_key,
            'secret_key':        secret_key,
            'selected_services': selected_services,
        }

    except (KeyboardInterrupt, EOFError):
        print("\n\n  Assessment dibatalkan.\n")
        return None
