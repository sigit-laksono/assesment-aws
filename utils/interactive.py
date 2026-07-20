"""
Interactive setup wizard untuk AWS Assessment Tool.
Menggunakan input() standar Python — kompatibel dengan semua terminal
termasuk WSL, SSH, dan terminal tanpa dukungan ANSI penuh.

Credentials diambil dari AWS CLI credential chain di runtime.
"""


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
        ("NLB (Network Load Balancer)",        "nlb",           True),
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
        ("Route 53",                           "route53",       False),
    ]),
    ("Security", [
        ("KMS (Key Management Service)",       "kms",           False),
        ("Secrets Manager",                    "secretsmanager", False),
        ("WAF (Web Application Firewall)",     "waf",           False),
    ]),
    ("Operations", [
        ("CloudWatch",                         "cloudwatch",    False),
        ("CloudTrail",                         "cloudtrail",    False),
        ("AWS Config",                         "config",        False),
    ]),
    ("Integration & Analytics", [
        ("SNS (Simple Notification Service)",  "sns",           False),
        ("MSK (Managed Kafka)",                "msk",           False),
        ("Amazon MQ",                          "amazonmq",      False),
        ("AWS Glue",                           "glue",          False),
    ]),
]


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


def _build_service_table() -> tuple[list, list]:
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
        for display_name, code, checked_by_default in services:
            flat.append((no, display_name, code))
            if checked_by_default:
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


def run_interactive_setup() -> dict | None:
    """
    Jalankan interactive setup wizard di terminal.

    Return dict:
        {
            'customer_name'    : str,
            'region'           : str,
            'selected_services': list[str],
        }
    Return None kalau user cancel.
    """
    flat_services, default_nos = _build_service_table()

    print("\n" + "=" * 58)
    print("   AWS Account Assessment Tool  v2.0")
    print("=" * 58)
    print("   Credentials: AWS CLI profile aktif di runtime ini")

    try:
        # ── 1. Customer Name ──────────────────────────────────────────────────
        print("\n[1/3] Informasi Customer")
        print("-" * 40)
        customer_name = _prompt("Nama Customer")
        if not customer_name:
            print("  Nama customer tidak boleh kosong.")
            return None

        region = _prompt("AWS Region", "ap-southeast-1")

        # ── 2. Service Selection ──────────────────────────────────────────────
        print("\n[2/3] Pilih Services")
        print("-" * 40)
        _print_service_table(flat_services, default_nos)

        total = len(flat_services)
        default_str = ",".join(str(n) for n in default_nos)
        print(f"\n  Masukkan nomor yang ingin di-scan, pisah dengan koma.")
        print(f"  Contoh: 1,3,7   |  'all' untuk semua  |  Enter untuk default")
        print()
        raw = input(f"  Pilihan [{default_str}]: ").strip()

        if not raw:
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

        selected_services = [
            code for (no, _, code) in flat_services if no in selected_nos
        ]

        # ── 3. Konfirmasi ─────────────────────────────────────────────────────
        print("\n[3/3] Konfirmasi")
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
            'selected_services': selected_services,
        }

    except (KeyboardInterrupt, EOFError):
        print("\n\n  Assessment dibatalkan.\n")
        return None
