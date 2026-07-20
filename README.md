# AWS Account Assessment Tool

Tool untuk melakukan assessment komprehensif terhadap akun AWS, menghasilkan laporan inventarisasi, analisis biaya, dan rekomendasi cost optimization. Output berupa HTML/PDF report untuk manusia dan JSON untuk AI/automation.

## Cara Pakai

### Mode Interaktif (Wizard)

```bash
python aws_assessment.py
```

Wizard terminal memandu pemilihan service, region, dan customer name.

### Mode CLI (Non-interaktif, Agent-friendly)

```bash
# Scan semua service
python cli.py --all --region ap-southeast-3

# Scan service tertentu saja
python cli.py --services ec2,s3,rds,iam --region ap-southeast-1

# Custom output folder + customer name
python cli.py --all --region ap-southeast-3 --customer "PT Contoh" --output ./output/scan-juli

# JSON only, tanpa HTML/PDF report
python cli.py --all --no-report

# Lihat service apa saja yang tersedia
python cli.py --list-services
```

**Opsi CLI:**

| Flag | Deskripsi |
|------|-----------|
| `--all` | Scan semua 28 service |
| `--services` | Comma-separated service codes |
| `--region` | AWS region (default: ap-southeast-1) |
| `--customer` | Nama customer untuk report |
| `--output` | Custom output directory |
| `--no-report` | Skip HTML/PDF, hanya simpan JSON |
| `--list-services` | Tampilkan daftar service codes |

---

## Service yang Tersedia (28)

```
alb, amazonmq, backup, cloudfront, cloudtrail, cloudwatch, config,
dynamodb, ebs, ec2, ecr, efs, eks, elasticache, glue, iam, kms,
lambda, msk, nat_gateway, nlb, rds, route53, s3, secretsmanager,
sns, vpc, waf
```

---

## Output

| File | Untuk siapa | Ukuran tipikal |
|------|-------------|----------------|
| `assessment_data_*.json` | AI / automation | ~15k token |
| `assessment_report_*.html` | Manusia (browser) | ~23k token |
| `assessment_report_*.pdf` | Manusia (cetak/share) | — |

JSON output berisi semua data mentah — AI agent bisa langsung baca dan analisis tanpa parsing HTML.

---

## Struktur Proyek

```
.
├── aws_assessment.py      # Entry point interaktif (wizard)
├── cli.py                 # Entry point CLI non-interaktif
├── collectors/            # Collector per service (boto3 langsung)
│   ├── billing.py
│   ├── compute.py         # EC2, Lambda, EKS, ALB, ECR
│   ├── storage.py         # S3, EBS, EFS, Backup
│   ├── database.py        # RDS, DynamoDB, ElastiCache
│   ├── network.py         # VPC, NAT, CloudFront, Route53, NLB
│   ├── security.py        # KMS, WAF, Secrets Manager, IAM
│   ├── integration.py     # SNS, MSK, AmazonMQ, Glue, CloudWatch
│   ├── operations.py      # CloudTrail, Config
│   └── cost_optimization.py
├── core/
│   ├── engine.py          # Session management + save JSON
│   └── reporter/          # Generate HTML/PDF report
├── templates/             # HTML template untuk report
├── utils/                 # Interactive wizard + helpers
├── tests/                 # pytest
├── output/                # Hasil assessment
└── requirements.txt
```

---

## Instalasi

```bash
# Virtual environment
python -m venv venv-win
.\venv-win\Scripts\Activate.ps1   # Windows PowerShell

# Dependencies
pip install -r requirements.txt
playwright install chromium        # Untuk PDF report
```

---

## Credentials

Diambil dari AWS CLI credential chain (`aws configure` atau environment variables). Tidak perlu file `.env`.

IAM Policy minimal: `ReadOnlyAccess` atau specific `Describe*` + `List*` + `ce:GetCostAndUsage`.

---

## Testing

```bash
python -m pytest tests/ -v
```

---

## Report Features

- **HTML**: Tabel dengan paginasi, search real-time, filter kategori, sidebar navigasi
- **PDF**: Auto-expansion semua data, Chart.js rendered, clean print mode
- **JSON**: Structured data mentah untuk automation/AI consumption

---

## Troubleshooting

| Problem | Solusi |
|---------|--------|
| Playwright error | `playwright install chromium` |
| Billing data kosong | AWS Cost Explorer perlu 24 jam setelah di-enable |
| Region tidak tersedia | Beberapa service belum available di semua region |
