# AWS Account Assessment Tool

Tool untuk melakukan assessment komprehensif terhadap akun AWS, menghasilkan laporan inventarisasi, analisis biaya, dan ringkasan sumber daya. Mendukung dua mode: **interaktif** (wizard terminal untuk manusia) dan **agentic** (dipanggil non-interaktif oleh AI agent).

## Dua Cara Pakai

### 1. Mode Interaktif (Wizard)

```bash
python aws_assessment.py
```

Sama seperti sebelumnya: pilih service interaktif, hasilnya HTML/PDF report di `output/`.

### 2. Mode Agentic (untuk AI Agent / Automation)

```python
from agentic import invoke, InvocationRequest, CapabilityRequest, AccountTarget, ExecutionContext
from agentic.registry import CapabilityRegistryImpl
from agentic.ec2_contract import register_ec2_inventory
from agentic.legacy_contracts import register_all_legacy_capabilities
from agentic.schemas.processor import CanonicalSchemaProcessor

# Setup registry (satu kali)
registry = CapabilityRegistryImpl()
register_ec2_inventory(registry)
register_all_legacy_capabilities(registry)

# Discover semua capability yang tersedia
manifest = registry.snapshot()
for cap in manifest.capabilities:
    print(f"{cap.capability_id}@{cap.version}")

# Panggil satu capability
request = InvocationRequest(
    capabilities=(CapabilityRequest(id="ec2.inventory", version="1.0.0"),),
    targets=(AccountTarget(account_id="123456789012"),),
    regions=("ap-southeast-1",),
    execution_context=ExecutionContext(
        caller_id="my-agent",
        correlation_id="run-001",
        purpose="monthly-check",
    ),
)
result = invoke(request, registry, CanonicalSchemaProcessor())
print(result.execution_status)  # "succeeded" atau "failed"
```

**Discovery**: `registry.snapshot()` mengembalikan `CapabilityManifest` — daftar machine-readable semua capability, versi, permission, dan allowed operations. Agent cukup baca ini untuk tahu apa yang tersedia.

**Multi-account / Multi-region**:

```python
request = InvocationRequest(
    capabilities=(CapabilityRequest(id="s3.inventory", version="1.0.0"),),
    targets=(
        AccountTarget(account_id="111111111111"),
        AccountTarget(account_id="222222222222", role_ref="arn:aws:iam::222222222222:role/assessor"),
    ),
    regions=("ap-southeast-1", "us-east-1"),
    execution_context=ExecutionContext(caller_id="agent", correlation_id="x", purpose="audit"),
)
```

Orchestrator membuat execution unit per kombinasi account × region (atau `aws-global` untuk service global) dan menjalankan dengan bounded concurrency (default 4).

---

## Capability yang Tersedia

| Service Code (wizard) | Capability ID | Scope |
|---|---|---|
| ec2 | `ec2.inventory` | regional |
| s3 | `s3.inventory` | global |
| rds | `rds.inventory` | regional |
| dynamodb | `dynamodb.inventory` | regional |
| ebs | `ebs.inventory` | regional |
| efs | `efs.inventory` | regional |
| vpc | `vpc.inventory` | regional |
| nat_gateway | `nat.inventory` | regional |
| cloudfront | `cloudfront.inventory` | global |
| route53 | `route53.inventory` | global |
| nlb | `nlb.inventory` | regional |
| iam | `iam.inventory` | global |
| kms | `kms.inventory` | regional |
| waf | `waf.inventory` | regional |
| cloudwatch | `cloudwatch.inventory` | regional |
| cloudtrail | `cloudtrail.inventory` | regional |
| config | `config.inventory` | regional |
| backup | `backup.inventory` | regional |
| secretsmanager | `secretsmanager.inventory` | regional |
| sns | `sns.inventory` | regional |
| msk | `msk.inventory` | regional |
| amazonmq | `amazonmq.inventory` | regional |
| glue | `glue.inventory` | regional |

Service yang belum dimigrasikan ke registry (fallback ke collector lama): `lambda`, `eks`, `alb`, `ecr`.

---

## Keamanan (Read-Only Guard)

Semua collector yang sudah dimigrasikan berjalan lewat `GuardedSession`. Setiap operasi AWS API dicek terhadap allowlist exact **sebelum** request dikirim ke AWS. Kalau kode collector mencoba operasi yang tidak ada di daftar read-only → ditolak langsung dengan error `guard-violation`. Agent tidak bisa secara tidak sengaja memutasi resource AWS.

IAM Policy minimal yang dibutuhkan: `Describe*` dan `List*` pada service terkait, plus `ce:GetCostAndUsage` untuk billing.

---

## Struktur Proyek

```text
.
├── aws_assessment.py          # Entry point interaktif (wizard)
├── agentic/                   # Layer agentic (invoke, registry, orchestrator)
│   ├── __init__.py            # Public API: invoke(), summarize(), list_runs()
│   ├── orchestrator.py        # invoke() — entry point agent
│   ├── registry.py            # Capability Registry immutable
│   ├── ec2_collector.py       # EC2 collector (granular filter/field)
│   ├── ec2_contract.py        # Register ec2.inventory@1.0.0
│   ├── legacy_collectors.py   # 8 collector lama dimigrasikan ke CollectorOutcome
│   ├── legacy_contracts.py    # Register semua capability lama ke registry
│   ├── legacy_adapter.py      # Bridge wizard → registry → collector → reporter
│   ├── executor.py            # Bounded concurrent executor
│   ├── session.py             # SessionFactory + GuardedSession (read-only guard)
│   ├── models.py              # Semua domain model (immutable dataclass)
│   ├── interfaces.py          # Protocol interfaces
│   ├── profile_registry.py    # Assessment Profile Registry
│   ├── summary.py             # Per-capability result summary
│   ├── runs.py                # list_runs() — scan output/agentic/runs/
│   ├── readiness.py           # assert_capability_ready() checklist
│   ├── schemas/               # JSON Schema + canonical processor
│   └── profiles/              # monthly-standard@1.0.0 (draft)
├── collectors/                # Collector lama (masih dipakai untuk fallback)
├── core/                      # Engine (session) + Reporter (HTML/PDF)
├── templates/                 # HTML/CSS/JS untuk report
├── tests/                     # 657 tests (pytest + hypothesis)
├── output/                    # Hasil assessment
└── requirements.txt
```

---

## Instalasi

```bash
# Buat virtual environment
python -m venv venv-win
.\venv-win\Scripts\Activate.ps1   # Windows PowerShell

# Install dependencies
pip install -r requirements.txt
playwright install chromium        # Untuk PDF report
```

Copy `.env.example` ke `.env` dan isi: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `CUSTOMER_NAME`.

---

## Testing

```bash
.\venv-win\Scripts\python.exe -m pytest tests/ -v
```

657 test, termasuk property-based tests (Hypothesis) untuk deterministic planning, canonical JSON round-trip, EC2 filter correctness, concurrency bounds, dan profile immutability.

---

## Report Output

### HTML Report
- Paginasi tabel, search real-time, filter kategori, sidebar navigasi.

### PDF Report
- Auto-expansion (semua data dicetak), Chart.js dirender, mode cetak bersih.

---

## Troubleshooting

- **Playwright Error**: Pastikan `playwright install chromium` sudah dijalankan.
- **Billing Data Kosong**: AWS Cost Explorer perlu 24 jam setelah di-enable.
- **GuardViolationError**: Collector mencoba operasi AWS yang tidak ada di allowlist — cek registrasi capability di `legacy_contracts.py`.
