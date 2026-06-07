# PRD: AWS Account Assessment Tool

> **Dokumen**: Product Requirements Document
> **Versi**: 1.3
> **Tanggal**: 6 Juni 2026
> **Status**: Draft (Updated)
> **Author**: Senior Product Manager (hasil scan source code)
> **Bahasa Produk**: Bahasa Indonesia
> **Referensi Teknis**: English (nama class, file path, AWS service)
> **Changelog v1.2**: IAM Inventory ditambahkan (4.18); Cost Optimization 2 rule baru (Graviton + Public IPv4) + field severity/action per finding; EC2 & ALB fields diperluas; Reporter direfactor ke package modular; unit test compute collector
> **Changelog v1.3**: Bugfix kritis — Graviton savings selalu $0.00 diperbaiki dengan menambah EC2 on-demand price table ke Pricing Engine (62 instance types, 20 region, multiplier-based); NLB kini collect `listener_count` sejajar ALB; HTML tabel ALB & NLB tampilkan kolom Listeners

---

## 1. Executive Summary

**AWS Account Assessment Tool** adalah CLI tool berbasis Python yang melakukan inventarisasi komprehensif terhadap satu akun AWS dan menghasilkan laporan profesional dalam tiga format: **JSON** (data mentah), **HTML** interaktif (dashboard dengan paginasi, search, filter, dan grafik biaya), serta **PDF** (versi cetak yang sudah dioptimalkan).

Tool ini ditujukan untuk **AWS Solutions Architect, MSP/Konsultan AWS, dan tim Cloud Operations** yang perlu melakukan _due diligence_ teknis sebelum migrasi, audit periodik, atau handover akun ke customer. Inti nilai (core value) tool ini adalah **otomasi pengumpulan data multi-service AWS dalam satu perintah** lalu mengubahnya menjadi dokumen presentasi yang siap dibagikan ke stakeholder bisnis dalam waktu hitungan menit, tanpa effort manual buka satu-satu console AWS.

Arsitektur v2.0 sudah modular: orchestrator → engine (session management) → collectors (per kategori AWS) → reporter package (HTML + PDF dengan Playwright). Cakupan saat ini **23+ layanan AWS** lintas 8 kategori (Compute, Storage, Database, Network, Security, Operations, Integration, Analytics) **plus analisis cost optimization otomatis (6 rule) dengan pricing real-time per region**.

---

## 2. Tech Stack

### Bahasa & Runtime
| Komponen | Teknologi | Versi |
|---|---|---|
| Bahasa Utama | Python | 3.x |
| Package Manager | pip + venv | — |

### Library / Dependencies
| Library | Fungsi |
|---|---|
| `boto3` (≥1.34.0) | AWS SDK untuk semua API call (STS, EC2, RDS, S3, Cost Explorer, Pricing API, dll) |
| `python-dotenv` (≥1.0.0) | Loader credential dari file `.env` |
| `playwright` (≥1.40.0, Chromium) | Engine PDF generation (menggantikan `pdfkit`/`wkhtmltopdf`) |

### Frontend Reporting Stack
- **HTML5** + **CSS3** (CSS Variables, Flexbox, Grid) → `templates/report_styles.css`
- **Vanilla JavaScript** untuk paginasi, search real-time, filter kategori, scrollspy → `templates/report_scripts.js`
- **Chart.js** (CDN) untuk grafik billing
- **Auto-inlining**: CSS & JS digabung saat runtime ke HTML standalone

### Storage & Persistensi
- **File-based**: JSON mentah, HTML, dan PDF disimpan ke folder `output/`
- **Pricing cache**: `data-pricing/extracted/<region>.json` — auto-cached per region dari AWS Pricing API
- **Tidak ada database** (stateless per-run, dengan file cache opsional)

### Konfigurasi
- `.env` → AWS credentials & customer info
- `services.md` → checklist layanan AWS yang akan di-scan (parser regex)

### Cloud APIs yang Digunakan
- **AWS STS** (validasi credential)
- **AWS Cost Explorer** (`ce`, di region `us-east-1`)
- **AWS Price List Query API** (`pricing`, endpoint `us-east-1`/`ap-south-1`/`eu-central-1`) — untuk data harga real-time
- **EC2, ECR, EKS, Lambda, ELBv2** (Compute)
- **S3, EFS, AWS Backup** (Storage)
- **RDS, DynamoDB, ElastiCache** (Database)
- **CloudFront, Route 53, VPC API** (Network)
- **KMS, WAFv2, Secrets Manager** (Security)
- **CloudWatch, CloudTrail, AWS Config** (Operations)
- **SNS, MSK (Kafka), Amazon MQ, Glue** (Integration & Analytics)

---

## 3. User Roles

Tool ini bersifat CLI single-user (tidak ada sistem auth/multi-tenant). Namun dari sudut pandang produk, ada tiga **user persona** yang menjadi target:

| Role / Persona | Akses & Perilaku | Output yang Dipakai |
|---|---|---|
| **AWS Solutions Architect / Konsultan** | Menjalankan tool dengan IAM user/role read-only milik customer. Butuh laporan rapi untuk presentasi. | HTML + PDF |
| **Cloud Engineer / DevOps Internal** | Audit periodik akun AWS sendiri. Butuh detail teknis & data mentah untuk analisis lanjutan. | JSON + HTML |
| **Customer / Stakeholder Bisnis** | Penerima laporan akhir. Tidak menjalankan tool, hanya membaca PDF/HTML. | PDF (terutama) |

### IAM Permission yang Dibutuhkan (di sisi AWS)
Minimal mencakup:
- `sts:GetCallerIdentity`
- `ce:GetCostAndUsage`
- `pricing:GetProducts` (opsional, untuk harga real-time — fallback ke tabel internal jika tidak ada)
- `Describe*` / `List*` pada semua service yang di-scan (EC2, RDS, S3, dll)
- `ec2:DescribeAddresses` (untuk deteksi Elastic IP idle)
- `elasticloadbalancing:DescribeTargetGroups`, `elasticloadbalancing:DescribeTargetHealth` (untuk deteksi LB tanpa target)

---

## 4. Existing Features

### 4.1 Credential & Session Management
- **Deskripsi**: Memuat AWS credentials dari `.env` dan membuat boto3 Session terpusat yang dipakai semua collector. Memvalidasi credential via STS sebelum proses berlanjut.
- **Entity / Data**: `AssessmentEngine.session`, `assessment_data['account_id']`, `assessment_data['region']`, `assessment_data['customer_name']`
- **File terkait**: `core/engine.py`, `.env`
- **Status**: ✅ Sudah ada

### 4.2 Konfigurasi Layanan via `services.md` (Checklist)
- **Deskripsi**: User mengaktifkan layanan AWS yang ingin di-scan dengan menandai `[x]` pada tabel Markdown. Parser regex membaca file ini, lalu engine menjalankan collector hanya untuk service yang aktif.
- **Entity / Data**: Mapping `service_name → service_code` di `service_mapping`, output `services_config[service_code] = {enabled, display_name}`
- **File terkait**: `services.md`, `utils/config_loader.py`
- **Status**: ✅ Sudah ada

### 4.3 Billing Data Collection (Cost Explorer)
- **Deskripsi**: Mengambil biaya bulan lalu (UnblendedCost & BlendedCost), breakdown per service, dan Top 10 cost drivers.
- **Entity / Data**: `billing_data`: `monthly_costs[]`, `service_costs{}`, `top_services[]`, `total_actual`, `total_blended`, `period`
- **AWS API**: `ce.get_cost_and_usage` (region `us-east-1`)
- **File terkait**: `collectors/billing.py`
- **Status**: ✅ Sudah ada

### 4.4 Inventarisasi Compute Services
- **Deskripsi**: Scan 5 layanan compute & containerization.
- **Entity / Data**:
  - **EC2**: `id`, `type`, `state`, `launch_time`, `platform`, `architecture`, `availability_zone`, `vpc_id`, `subnet_id`, `public_ip`, `ebs_optimized`, `name` (dari tag), `environment` (dari tag)
  - **Lambda**: `name`, `runtime`, `memory`, `last_modified`
  - **EKS**: `name`, `status`, `version`, `endpoint`, `created_at`
  - **ALB**: `name`, `arn`, `dns`, `scheme`, `state`, `vpc_id`, `availability_zones`, `listener_count` (via `describe_listeners`)
  - **ECR**: `name`, `uri`, `image_count`, `image_tag_mutability`, `scan_on_push`
- **File terkait**: `collectors/compute.py`
- **Status**: ✅ Sudah ada

### 4.5 Inventarisasi Storage Services
- **Deskripsi**: Scan layanan penyimpanan dan backup.
- **Entity / Data**:
  - **S3**: `name`, `creation_date`
  - **EBS**: `id`, `size`, `type`, `state`, `iops`, `encrypted`
  - **EFS**: `id`, `name`, `life_cycle_state`, `number_of_mount_targets`, `size_in_bytes`, `encrypted`
  - **AWS Backup**: `vaults[]` (number_of_recovery_points), `plans[]`
- **File terkait**: `collectors/storage.py`
- **Status**: ✅ Sudah ada

### 4.6 Inventarisasi Database Services
- **Deskripsi**: Scan database engine yang dikelola.
- **Entity / Data**:
  - **RDS**: `id`, `engine`, `class`, `status`
  - **DynamoDB**: `name`, `status`, `item_count`, `size_bytes`
  - **ElastiCache**: `id`, `engine`, `engine_version`, `node_type`, `status`, `num_nodes`
- **File terkait**: `collectors/database.py`
- **Status**: ✅ Sudah ada

### 4.7 Inventarisasi Networking Services
- **Deskripsi**: Scan komponen jaringan & content delivery.
- **Entity / Data**:
  - **VPC**: `id`, `name`, `cidr`, `is_default`, `state`
  - **NAT Gateway**: `id`, `vpc_id`, `subnet_id`, `state`, `connectivity_type`
  - **CloudFront**: `id`, `domain`, `status`, `enabled`
  - **ALB** (via `collectors/compute.py`): `name`, `arn`, `dns`, `scheme`, `state`, `vpc_id`, `availability_zones`, `listener_count`
  - **NLB** (via `collectors/network.py`): `name`, `arn`, `dns`, `scheme`, `state`, `vpc_id`, `availability_zones`, `listener_count`
  - **Route 53**: `id`, `name`, `type` (Public/Private), `record_count`
- **File terkait**: `collectors/network.py`
- **Status**: ✅ Sudah ada

### 4.8 Inventarisasi Security Services
- **Deskripsi**: Scan layanan keamanan & manajemen kunci.
- **Entity / Data**:
  - **KMS**: hanya customer-managed keys (`AWS managed` di-skip), `id`, `state`, `enabled`, `created_date`
  - **WAFv2**: scope `REGIONAL` + `CLOUDFRONT`, `name`, `id`, `arn`
  - **Secrets Manager**: `name`, `description`, `rotation_enabled`, `last_changed_date`
  - **IAM**: lihat **4.18** di bawah
- **File terkait**: `collectors/security.py`
- **Status**: ✅ Sudah ada

### 4.9 Inventarisasi Operations Services
- **Deskripsi**: Scan layanan audit & monitoring.
- **Entity / Data**:
  - **CloudTrail**: `name`, `is_logging`, `is_multi_region`, `s3_bucket`
  - **AWS Config**: `name`, `is_recording`, `record_all`
  - **CloudWatch**: `alarms[]` → `name`, `state`, `metric`, `namespace`
- **File terkait**: `collectors/operations.py`, `collectors/integration.py` (CloudWatch)
- **Status**: ✅ Sudah ada

### 4.10 Inventarisasi Integration & Analytics
- **Deskripsi**: Scan messaging, streaming, dan ETL services.
- **Entity / Data**:
  - **SNS**: `name`, `display_name`, `subscriptions_confirmed`, `subscriptions_pending`
  - **MSK**: `name`, `cluster_type`, `state`, `creation_time`
  - **Amazon MQ**: `name`, `engine_type`, `broker_state`, `deployment_mode`, `host_instance_type`
  - **AWS Glue**: `databases[]`, `jobs[]` (dengan `glue_version`, `max_capacity`)
- **File terkait**: `collectors/integration.py`
- **Status**: ✅ Sudah ada

### 4.11 Penyimpanan Data Mentah (JSON)
- **Deskripsi**: Semua hasil collection disimpan ke `output/assessment_data_<timestamp>.json` dengan `DecimalEncoder` untuk handle tipe Decimal dari Cost Explorer.
- **Entity / Data**: Object `assessment_data` (full payload termasuk `cost_optimization`)
- **File terkait**: `core/engine.py` (`save_data`), `utils/helpers.py`
- **Status**: ✅ Sudah ada

### 4.12 Generate HTML Report Interaktif
- **Deskripsi**: Render dashboard HTML standalone dengan placeholder substitution + auto-inlining CSS/JS. Mendukung paginasi 10 baris/halaman, real-time search, filter kategori, sidebar scrollspy, Chart.js billing, dan section Cost Optimization.
- **Entity / Data**: Template placeholder (`{{CUSTOMER_NAME}}`, `{{TOP_COST_DRIVERS}}`, `{{SERVICES_INVENTORY_CONTENT}}`, `{{SUMMARY_SERVICES}}`, `{{COST_OPTIMIZATION}}`, dll)
- **Arsitektur Reporter** (refactored dari `core/reporter.py` ke package modular):
  | File | Tanggung Jawab |
  |---|---|
  | `core/reporter/__init__.py` | Public API — re-export `generate_html_report`, `generate_pdf_report` |
  | `core/reporter/html_report.py` | Orchestrator: load template, inline CSS/JS, rakit semua section |
  | `core/reporter/pdf_report.py` | PDF via Playwright headless Chromium |
  | `core/reporter/section_inventory.py` | Render tabel HTML per AWS service (ALB & NLB include kolom Listeners) |
  | `core/reporter/section_summary.py` | Tabel ringkasan jumlah resource (Executive Summary) |
  | `core/reporter/section_cost.py` | Tabel findings Cost Optimization + summary cards |
- **File terkait**: `core/reporter/`, `templates/report_template.html`, `templates/report_styles.css`, `templates/report_scripts.js`
- **Status**: ✅ Sudah ada

### 4.13 Generate PDF Report (Playwright)
- **Deskripsi**: Render PDF profesional menggunakan headless Chromium. Otomatis menonaktifkan paginasi & filter agar **semua resource** muncul dalam satu dokumen, plus header/footer dengan nomor halaman.
- **Entity / Data**: Format A4, margin 1cm, `print_background=true`
- **File terkait**: `core/reporter/pdf_report.py`
- **Status**: ✅ Sudah ada

### 4.14 Orchestrator Pipeline
- **Deskripsi**: Class `AWSAssessment` mewarisi `AssessmentEngine` dan menyimpan `inventory_map` (dict service_code → collector function). Eksekusi 6 tahap: Validate → Billing → Load Config → Inventory Loop → Cost Optimization → Save & Report.
- **File terkait**: `aws_assessment.py`
- **Status**: ✅ Sudah ada

### 4.15 Cost Optimization Detection
- **Deskripsi**: Modul analisis otomatis yang mendeteksi resource AWS yang **terbuang/waste atau tidak efisien** berdasarkan **6 rule** dengan confidence tinggi (tanpa false-positive), kemudian menghitung estimasi penghematan bulanan berdasarkan harga aktual per region (dari Pricing Engine 4.16).
- **Entity / Data**: `assessment_data['cost_optimization']` dengan field:
  - `total_potential_savings`: estimasi total penghematan USD/bulan
  - `findings[]`: list finding, masing-masing memiliki `rule`, `category`, `resource_id`, `details`, `estimated_monthly_cost`, `severity` (`low`/`medium`/`high`), `action` (rekomendasi tindakan)
  - `summary{}`: agregasi per kategori (`count`, `savings`)
  - `price_region`, `price_source`, `price_region_fallback`, `price_region_note`
- **Rule yang diimplementasi**:
  | # | Rule | Deteksi | Sumber Data | Severity |
  |---|---|---|---|---|
  | 1 | `ebs_unattached` | EBS volume state `available` (tidak dipakai) | `assessment_data['services']['ebs']` | medium |
  | 2 | `ec2_stopped_ebs` | EC2 stopped tapi disk EBS masih attached (tetap ditagih) | Cross-reference EC2 + EBS | medium |
  | 3 | `eip_idle` | Elastic IP tidak ter-assign ke resource | `ec2.describe_addresses()` (API call tambahan) | low |
  | 4 | `lb_no_target` | ALB/NLB tanpa target group atau tanpa target aktif | `elbv2.describe_target_groups()` + `describe_target_health()` | medium |
  | 5 | `graviton_eligible` | Linux x86_64 instance dari family yang punya Graviton equivalent (m5→m7g, c5→c7g, r5→r7g, t3→t4g, dll). `estimated_monthly_cost` = harga instance × 730 jam × savings_pct, dari `pricing['ec2_ondemand']` | `assessment_data['services']['ec2']` (field `platform` + `architecture`) | medium |
  | 6 | `public_ipv4_cost` | EC2 instance dengan Public IPv4 (ditagih $0.005/jam sejak Feb 2024) | `assessment_data['services']['ec2']` (field `public_ip`) | low |
- **AWS API tambahan**: `ec2:DescribeAddresses`, `elasticloadbalancing:DescribeTargetGroups`, `elasticloadbalancing:DescribeTargetHealth`
- **File terkait**: `collectors/cost_optimization.py`
- **Status**: ✅ Sudah ada

### 4.16 AWS Pricing Engine
- **Deskripsi**: Modul independen untuk resolve harga AWS On-Demand secara akurat per region. Digunakan oleh cost optimization untuk estimasi penghematan. Arsitektur 4 lapis resolusi:
  1. **AWS Price List Query API** (real-time via boto3, gratis, butuh permission `pricing:GetProducts`)
  2. **File cache** di `data-pricing/extracted/<region>.json` (auto-update setelah API fetch)
  3. **Tabel internal** `_REGION_PRICING` (13 region populer, hardcoded)
  4. **Fallback us-east-1** + flag warning
- **Entity / Data — Pricing dict** (selalu tersedia di semua path resolusi):
  | Key | Tipe | Sumber | Keterangan |
  |---|---|---|---|
  | `ebs` | `dict` | API → cache → tabel | Harga per GB/bulan per volume type (gp2/gp3/io1/io2/st1/sc1/standard) |
  | `eip_hr` | `float` | API → cache → tabel | Elastic IP idle, USD/jam |
  | `alb_hr` | `float` | API → cache → tabel | ALB fixed cost, USD/jam |
  | `nlb_hr` | `float` | API → cache → tabel | NLB fixed cost, USD/jam |
  | `ec2_ondemand` | `dict` | Tabel internal × multiplier | On-demand Linux per instance type, USD/jam — **62 instance types**, 8 family (t3/t3a/m5/m5a/c5/c5a/r5/r5a) |
- **EC2 Pricing Design** (`ec2_ondemand`):
  - Base prices di `_EC2_BASE_PRICES` (us-east-1 sebagai referensi)
  - Per-region scaling via `_EC2_REGION_MULTIPLIER` (20 region terdaftar, default ×1.15 untuk region lain)
  - Dihitung di `_merge()` pada **semua path** (cache, internal table, fallback) — tidak pernah `None`
  - Digunakan oleh rule `graviton_eligible` untuk estimasi USD savings bulanan
- **Cache file**: `data-pricing/extracted/<region>.json` (auto-persist + merge, tidak ada TTL saat ini)
- **Region prefix map** (`_REGION_PREFIX_MAP`): konversi region code ke AWS usagetype prefix untuk filter Pricing API
- **Public API functions**:
  | Function | Deskripsi |
  |---|---|
  | `resolve_pricing(session, region)` | Full resolve: coba API → merge cache + tabel. Dipakai saat assessment. |
  | `fetch_pricing(session, region)` | Fetch dari AWS Pricing API, simpan cache. |
  | `get_pricing(region)` | Resolve tanpa API (offline mode). |
  | `get_cache_info(region)` | Metadata cache: kapan terakhir fetch, komponen tersedia. |
- **File terkait**: `utils/pricing.py`, `data-pricing/extracted/`
- **Status**: ✅ Sudah ada

### 4.17 Test Script Cost Optimization
- **Deskripsi**: Script testing sederhana untuk validasi full flow `run_cost_optimization` dengan data simulasi (2 EBS unattached di region `ap-southeast-3`).
- **File terkait**: `scripts/test_full_flow.py`
- **Status**: ✅ Sudah ada

### 4.18 Inventarisasi IAM (Summary Level)
- **Deskripsi**: Collector `inventory_iam` di `collectors/security.py` mengumpulkan data ringkasan IAM tanpa PII — hanya angka agregat dan konfigurasi policy. Dirancang untuk security posture awareness tanpa perlu `iam:ListUsers` per-user.
- **Entity / Data**: `assessment_data['services']['iam']` dengan field:
  | Field | Sumber AWS API | Keterangan |
  |---|---|---|
  | `users_count` | `iam:GetAccountSummary` → `Users` | Jumlah IAM user |
  | `groups_count` | `iam:GetAccountSummary` → `Groups` | Jumlah IAM group |
  | `roles_count` | `iam:GetAccountSummary` → `Roles` | Jumlah IAM role |
  | `policies_count` | `iam:GetAccountSummary` → `Policies` | Jumlah customer-managed policy |
  | `mfa_devices_in_use` | `iam:GetAccountSummary` → `MFADevicesInUse` | Jumlah MFA device aktif |
  | `account_access_keys` | `iam:GetAccountSummary` → `AccountAccessKeysPresent` | Access key di root account (risiko tinggi jika > 0) |
  | `root_mfa_enabled` | `iam:GetAccountSummary` → `AccountMFAEnabled` | Root user MFA status |
  | `password_policy_set` | `iam:GetAccountPasswordPolicy` | Ada/tidaknya password policy |
  | `min_password_length` | Password policy | Panjang minimum password |
  | `require_symbols/numbers/uppercase/lowercase` | Password policy | Kompleksitas password |
  | `password_reuse_prevention` | Password policy | Jumlah password lama yang tidak bisa dipakai ulang |
  | `max_password_age` | Password policy | Masa berlaku password (hari) |
- **AWS API**: `iam:GetAccountSummary`, `iam:GetAccountPasswordPolicy`
- **IAM Permission**: `iam:GetAccountSummary`, `iam:GetAccountPasswordPolicy`
- **File terkait**: `collectors/security.py` (function `inventory_iam`)
- **Catatan**: Collector ini sudah terintegrasi ke orchestrator `aws_assessment.py` sebagai `'iam': inventory_iam` di `inventory_map`. Ditampilkan di section summary HTML report.
- **Status**: ✅ Sudah ada

### 4.19 Unit Test Compute Collector
- **Deskripsi**: Test suite untuk `collectors/compute.py` menggunakan mock boto3 — memvalidasi parsing field baru EC2 (platform, architecture, tags, public_ip, dll) dan listener count ALB.
- **File terkait**: `tests/test_compute_collector.py`
- **Status**: ✅ Sudah ada

---

## 5. Recommended New Features

Berikut 5 rekomendasi fitur baru yang **logis dikembangkan** berdasarkan konteks tool inventory & assessment AWS, diurutkan berdasarkan dampak bisnis:

---

### 5.1 Security Posture Scoring & Findings 🔒
**Priority: HIGH**

- **Problem**: Saat ini tool melakukan **inventarisasi** dan **cost analysis**, tetapi belum mengevaluasi **kualitas konfigurasi keamanan**. Data yang dikumpulkan sudah sangat dekat untuk dianalisis: ada `EBS.encrypted`, `EFS.encrypted`, `KMS.enabled`, `CloudTrail.is_multi_region`, `SecretsManager.rotation_enabled`, dll. Customer hampir selalu menanyakan _"Akun saya sudah aman atau belum?"_.
- **User Story**:
  - **US-001**: Sebagai AWS Solutions Architect, saya ingin melihat daftar _security findings_ di akun customer beserta skor keseluruhan, sehingga saya bisa langsung memberikan rekomendasi prioritas tanpa cek manual.
- **Functional Requirements**:
  | ID | Requirement | Priority |
  |---|---|---|
  | FR-1.1 | Modul baru `collectors/security_findings.py` yang menjalankan rule check terhadap data yang sudah ada di `assessment_data` (post-processing, sebagian besar tidak perlu API tambahan) | High |
  | FR-1.2 | Minimal 10 rule built-in: S3 bucket public-read, EBS unencrypted, RDS unencrypted, CloudTrail tidak multi-region, KMS rotation disabled, Secrets Manager rotation disabled, IAM root MFA, default VPC masih dipakai, security group `0.0.0.0/0` port sensitif, KMS key `PendingDeletion` | High |
  | FR-1.3 | Setiap finding: `severity` (Critical/High/Medium/Low/Info), `category`, `resource_id`, `description`, `remediation` (link AWS docs) | High |
  | FR-1.4 | Section baru di HTML report: **Security Posture** dengan progress bar skor 0–100 dan tabel findings filterable per severity | High |
  | FR-1.5 | Findings muncul di executive summary PDF (top 5 critical) | Medium |
- **Technical Considerations**:
  - API tambahan: `s3.get_bucket_acl`, `s3.get_bucket_policy_status`, `ec2.describe_security_groups`, `iam.get_account_summary`
  - **Fondasi sudah tersedia**: IAM inventory (4.18) sudah mengumpulkan `root_mfa_enabled`, `password_policy_set`, `account_access_keys` — data ini bisa langsung dipakai sebagai input rule security findings
  - Reuse `assessment_data['security_findings']` yang **sudah tersedia** di `AssessmentEngine` (field kosong, belum dipakai)
  - Skor: `100 - (Critical*15 + High*8 + Medium*3 + Low*1)`, floor 0
  - Template baru: placeholder `{{SECURITY_FINDINGS}}`, `{{SECURITY_SCORE}}`
  - Pola implementasi bisa mengikuti **arsitektur `cost_optimization.py`** (rule functions + entry point + `section_cost.py` analog untuk `section_security.py` di reporter package)
  - Integrasi opsional: **AWS Security Hub** & **GuardDuty** (sudah ada di `services.md` tapi belum implemented)
- **Breaking Changes**: Tidak ada (additive)

---

### 5.2 Multi-Account Assessment via AWS Organizations 🏢
**Priority: HIGH**

- **Problem**: Satu run = satu akun AWS. Untuk customer enterprise dengan AWS Organizations (5–50 akun), konsultan harus copy-paste credential berulang kali — tidak scalable.
- **User Story**:
  - **US-002**: Sebagai MSP yang mengelola customer enterprise, saya ingin menjalankan satu perintah dan tool men-scan semua akun di AWS Organizations, sehingga saya bisa menghasilkan laporan konsolidasi.
- **Functional Requirements**:
  | ID | Requirement | Priority |
  |---|---|---|
  | FR-2.1 | Mode `--multi-account` yang membaca daftar akun dari AWS Organizations API atau file `accounts.yaml` | High |
  | FR-2.2 | Setiap akun di-assess via `sts:AssumeRole` ke role yang sama (mis. `OrganizationAccountAccessRole`) | High |
  | FR-2.3 | Output per-akun ditambah satu **consolidated report** (HTML + PDF) | High |
  | FR-2.4 | Eksekusi paralel (thread pool) dengan rate-limit yang aman | Medium |
  | FR-2.5 | Penanganan akun yang gagal: lanjutkan akun lain & tampilkan "Failed Accounts" section | High |
- **Technical Considerations**:
  - API tambahan: `organizations.list_accounts`, `sts.assume_role`
  - Refactor `AssessmentEngine.__init__` → DI pattern (terima session dari luar)
  - Modul baru: `core/orchestrator_multi.py`
  - Output: `output/<account_id>/...`
- **Breaking Changes**: Tidak ada untuk single-account flow (opt-in via flag)

---

### 5.3 Historical Comparison & Drift Detection 📊
**Priority: MEDIUM**

- **Problem**: Setiap run menghasilkan JSON baru tapi tidak pernah dibandingkan. Pertanyaan _"Apa saja resource baru bulan ini?"_, _"Cost growth-nya berapa?"_, _"Ada konfigurasi berubah?"_ tidak bisa dijawab.
- **User Story**:
  - **US-003**: Sebagai Cloud Engineer, saya ingin membandingkan dua hasil assessment, sehingga saya bisa melihat resource yang ditambah/dihapus/berubah.
- **Functional Requirements**:
  | ID | Requirement | Priority |
  |---|---|---|
  | FR-3.1 | Command `python aws_assessment.py --compare <old.json> <new.json>` | High |
  | FR-3.2 | Diff per service: `added[]`, `removed[]`, `changed[]` | High |
  | FR-3.3 | Cost growth chart: bandingkan `total_actual` | Medium |
  | FR-3.4 | Output: `output/comparison_<timestamp>.html` | Medium |
  | FR-3.5 | Highlight drift sensitif keamanan (encryption berubah `true` → `false`) | High |
- **Technical Considerations**:
  - Pure post-processing (baca dua JSON, **tanpa API call**)
  - Library: `deepdiff` (tambah ke `requirements.txt`)
  - Re-use template HTML + section khusus `{{COMPARISON_CONTENT}}`
- **Breaking Changes**: Tidak ada (subcommand baru)

---

### 5.4 Tag Compliance & Resource Inventory Export 🏷️
**Priority: MEDIUM**

- **Problem**: Banyak organisasi punya tagging policy wajib (Environment, Owner, CostCenter). Tool tidak memeriksa/menampilkan tags — kurang berguna untuk governance & cost allocation.
- **User Story**:
  - **US-004**: Sebagai Cloud Governance Officer, saya ingin melihat resource yang tidak memenuhi tagging policy dan mengekspor inventory ke Excel.
- **Functional Requirements**:
  | ID | Requirement | Priority |
  |---|---|---|
  | FR-4.1 | Setiap collector menambahkan field `tags` (dict) ke resource | High |
  | FR-4.2 | File `tagging_policy.yaml` (opsional) untuk required tag keys | Medium |
  | FR-4.3 | Section "Tag Compliance" di report dengan compliance percentage per service | Medium |
  | FR-4.4 | Export "Download Excel" di HTML report → `assessment_<ts>.xlsx` | Low |
  | FR-4.5 | Backward compatible: tanpa policy file, tampilkan tag tanpa scoring | High |
- **Technical Considerations**:
  - Modifikasi tiap collector untuk include `Tags` dari response boto3
  - Library: `openpyxl` untuk Excel
  - Alternatif efisien: **Resource Groups Tagging API** (`resourcegroupstaggingapi.get_resources`)
- **Breaking Changes**: Format JSON output berubah (tambah field `tags` per resource)

---

### 5.5 Expanded Cost Optimization Rules 💰
**Priority: MEDIUM**

- **Problem**: Cost optimization yang sudah ada (4.15) hanya cover 4 rule waste detection. Masih banyak pola pemborosan yang bisa dideteksi dari data inventory yang sudah tersedia dan dari API tambahan (Trusted Advisor, CloudWatch metrics).
- **User Story**:
  - **US-005**: Sebagai Konsultan AWS, saya ingin tool mendeteksi lebih banyak pola waste & right-sizing opportunities, sehingga estimasi penghematan lebih komprehensif.
- **Functional Requirements**:
  | ID | Requirement | Priority |
  |---|---|---|
  | FR-5.1 | Rule tambahan: (a) Orphaned EBS snapshots (volume sudah dihapus), (b) EC2 right-sizing via CloudWatch CPU utilization < 10% selama 14 hari, (c) Old-gen instance types (m3/c3/t1 → m5/c5/t3), (d) RDS idle (no connections > 7 hari), (e) S3 lifecycle missing pada bucket besar | High |
  | FR-5.2 | Integrasi opsional dengan **AWS Trusted Advisor** checks (butuh Business/Enterprise Support) | Medium |
  | FR-5.3 | Integrasi opsional dengan **AWS Compute Optimizer** API untuk rekomendasi instance sizing | Medium |
  | FR-5.4 | Kategori finding: `waste` (sudah ada) vs `right_sizing` (baru) — visualisasi terpisah di report | High |
  | FR-5.5 | Export rekomendasi ke CSV terpisah (`cost_optimization_<ts>.csv`) untuk action plan | Low |
- **Technical Considerations**:
  - API tambahan: `ec2.describe_snapshots(OwnerIds=['self'])`, `cloudwatch.get_metric_statistics`, `support.describe_trusted_advisor_checks`, `compute-optimizer.get_ec2_instance_recommendations`
  - Extend arsitektur `collectors/cost_optimization.py` → tambah rule functions di file yang sama atau pecah ke `collectors/cost_rightsizing.py`
  - Pricing engine (`utils/pricing.py`) sudah mendukung EBS price per type — tinggal tambah instance pricing untuk right-sizing
  - Tambah tabel pricing untuk EC2 instance types (bisa fetch dari Pricing API)
- **Breaking Changes**: Tidak ada (extend `cost_optimization.findings[]` dengan rule baru)

---

## 6. Open Questions

Hal-hal yang perlu dikonfirmasi dengan tim sebelum development dimulai:

1. **Target customer utama**: tool ini lebih banyak dipakai untuk _pre-sales assessment_ (sekali pakai) atau _ongoing audit_ (rutin bulanan)? Menentukan prioritas fitur **5.3 Historical Comparison** vs **5.2 Multi-Account**.

2. **Cakupan keamanan (5.1)**: cukup pakai **rule built-in sederhana** (cepat, tanpa setup tambahan) atau wajib integrasi **Security Hub** & **GuardDuty** (lebih kaya, tapi customer harus enable services berbayar)?

3. **Right-sizing data source (5.5)**: pakai **CloudWatch metrics** (14 hari data, butuh API call per instance) atau **Compute Optimizer** (sudah jadi rekomendasi, tapi harus enabled)?

4. **Tag compliance format (5.4)**: cukup `yaml` sederhana, atau compatible dengan **AWS Organizations Tag Policies** (JSON)?

5. **Format laporan tambahan**: perlu **Excel (.xlsx)** dan/atau **PowerPoint (.pptx)** untuk presentasi? Ini mengubah scope dependency.

6. **Bahasa laporan**: saat ini campuran ID + EN. Perlu fitur **i18n** (toggle bahasa report HTML) untuk customer multinasional?

7. **Multi-account credentials (5.2)**: credential role-arn disimpan di file plain-text atau pakai **AWS SSO / IAM Identity Center**?

8. **Region scope**: saat ini scan hanya satu region. Perlu mode `--all-regions`? (berdampak besar ke jumlah API call dan waktu eksekusi)

9. **Performance**: untuk akun besar (1000+ EC2, ratusan snapshot), perlu **paralelisme antar collector** dan paginator yang lebih robust?

10. **Distribusi tool**: tetap CLI `pip install` atau perlu **Docker image** / **standalone binary** (PyInstaller) untuk tim non-Python?

11. **Pricing cache refresh**: berapa lama cache `data-pricing/extracted/<region>.json` dianggap valid sebelum force re-fetch? (Saat ini tidak ada TTL — selalu coba fetch, fallback ke cache.)

---

## Lampiran: Ringkasan Arsitektur Saat Ini

```
aws_assessment.py (Orchestrator)
    └── core/engine.py (AssessmentEngine: session + data store)
        ├── collectors/billing.py          → Cost Explorer
        ├── collectors/compute.py          → EC2 (+tags, platform, arch, public_ip), Lambda, EKS, ALB (+listener_count), ECR
        ├── collectors/storage.py          → S3, EBS, EFS, Backup
        ├── collectors/database.py         → RDS, DynamoDB, ElastiCache
        ├── collectors/network.py          → VPC, NAT, CloudFront, ELB, NLB (+listener_count), Route 53
        ├── collectors/security.py         → KMS, WAF, Secrets Manager, IAM (summary)
        ├── collectors/integration.py      → SNS, MSK, MQ, Glue, CloudWatch
        ├── collectors/operations.py       → CloudTrail, Config
        └── collectors/cost_optimization.py → Waste detection (6 rules: EBS, EC2-EBS, EIP, LB, Graviton, IPv4)
    └── utils/
        ├── pricing.py        → AWS Pricing Engine (API → cache → tabel → fallback) + EC2 on-demand table (62 types, 20 region)
        ├── config_loader.py  → parser services.md
        └── helpers.py        → DecimalEncoder
    └── core/reporter/        (package — refactored dari reporter.py monolith)
        ├── __init__.py           → public API re-export
        ├── html_report.py        → orchestrator HTML
        ├── pdf_report.py         → Playwright headless Chromium
        ├── section_inventory.py  → tabel inventory per service
        ├── section_summary.py    → ringkasan jumlah resource
        └── section_cost.py       → cost optimization findings
        └── templates/ (HTML + CSS + JS terpisah, auto-inlined)
    └── data-pricing/extracted/   → File cache harga per region (JSON)
    └── scripts/test_full_flow.py → Integration test cost optimization
    └── tests/test_compute_collector.py → Unit test compute collector
```

**Alur eksekusi**: `validate_credentials` → `get_billing_data` → `load_services_config` → loop `inventory_map` → `run_cost_optimization` → `save_data` → `generate_html_report` → `generate_pdf_report`.

---

> **Catatan Akhir**: Semua rekomendasi di atas dirancang **additive** dan kompatibel dengan arsitektur modular v2.0. Pola yang sudah terbukti baik — `cost_optimization.py` dengan rule functions + pricing engine terpisah, reporter sebagai package dengan section modules — bisa direplikasi untuk fitur Security Findings (5.1) dan Extended Cost Rules (5.5). Fitur Multi-Account (5.2) dan Comparison (5.3) adalah subcommand baru yang tidak mengganggu flow existing. IAM inventory (4.18) sudah menyediakan fondasi data untuk rule-rule di 5.1 (root MFA, password policy, access keys).
