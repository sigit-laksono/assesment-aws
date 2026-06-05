# PRD: AWS Account Assessment Tool

> **Dokumen**: Product Requirements Document
> **Versi**: 1.0
> **Tanggal**: 5 Juni 2026
> **Status**: Draft
> **Author**: Senior Product Manager (hasil scan source code)
> **Bahasa Produk**: Bahasa Indonesia
> **Referensi Teknis**: English (nama class, file path, AWS service)

---

## 1. Executive Summary

**AWS Account Assessment Tool** adalah CLI tool berbasis Python yang melakukan inventarisasi komprehensif terhadap satu akun AWS dan menghasilkan laporan profesional dalam tiga format: **JSON** (data mentah), **HTML** interaktif (dashboard dengan paginasi, search, filter, dan grafik biaya), serta **PDF** (versi cetak yang sudah dioptimalkan).

Tool ini ditujukan untuk **AWS Solutions Architect, MSP/Konsultan AWS, dan tim Cloud Operations** yang perlu melakukan _due diligence_ teknis sebelum migrasi, audit periodik, atau handover akun ke customer. Inti nilai (core value) tool ini adalah **otomasi pengumpulan data multi-service AWS dalam satu perintah** lalu mengubahnya menjadi dokumen presentasi yang siap dibagikan ke stakeholder bisnis dalam waktu hitungan menit, tanpa effort manual buka satu-satu console AWS.

Arsitektur v2.0 sudah modular: orchestrator → engine (session management) → collectors (per kategori AWS) → reporter (HTML + PDF dengan Playwright). Cakupan saat ini **22+ layanan AWS** lintas 8 kategori (Compute, Storage, Database, Network, Security, Operations, Integration, Analytics).

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
| `boto3` (≥1.34.0) | AWS SDK untuk semua API call (STS, EC2, RDS, S3, dll) |
| `python-dotenv` (≥1.0.0) | Loader credential dari file `.env` |
| `playwright` (≥1.40.0, Chromium) | Engine PDF generation (menggantikan `pdfkit`/`wkhtmltopdf`) |

### Frontend Reporting Stack
- **HTML5** + **CSS3** (CSS Variables, Flexbox, Grid) → `templates/report_styles.css`
- **Vanilla JavaScript** untuk paginasi, search real-time, filter kategori, scrollspy → `templates/report_scripts.js`
- **Chart.js** (CDN) untuk grafik billing
- **Auto-inlining**: CSS & JS digabung saat runtime ke HTML standalone

### Storage & Persistensi
- **File-based**: JSON mentah, HTML, dan PDF disimpan ke folder `output/`
- **Tidak ada database** (stateless per-run)

### Konfigurasi
- `.env` → AWS credentials & customer info
- `services.md` → checklist layanan AWS yang akan di-scan (parser regex)

### Cloud APIs yang Digunakan
- **AWS STS** (validasi credential)
- **AWS Cost Explorer** (`ce`, di region `us-east-1`)
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
- `Describe*` / `List*` pada semua service yang di-scan (EC2, RDS, S3, dll)

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
  - **EC2**: `id`, `type`, `state`, `launch_time`
  - **Lambda**: `name`, `runtime`, `memory`, `last_modified`
  - **EKS**: `name`, `status`, `version`, `endpoint`, `created_at`
  - **ALB**: `name`, `arn`, `dns`, `scheme`, `state`, `vpc_id`, `availability_zones`
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
  - **ELB / ALB / NLB**: `name`, `type`, `scheme`, `state`, `dns`
  - **Route 53**: `id`, `name`, `type` (Public/Private), `record_count`
- **File terkait**: `collectors/network.py`
- **Status**: ✅ Sudah ada

### 4.8 Inventarisasi Security Services
- **Deskripsi**: Scan layanan keamanan & manajemen kunci.
- **Entity / Data**:
  - **KMS**: hanya customer-managed keys (`AWS managed` di-skip), `id`, `state`, `enabled`, `created_date`
  - **WAFv2**: scope `REGIONAL` + `CLOUDFRONT`, `name`, `id`, `arn`
  - **Secrets Manager**: `name`, `description`, `rotation_enabled`, `last_changed_date`
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
- **Entity / Data**: Object `assessment_data` (full payload)
- **File terkait**: `core/engine.py` (`save_data`), `utils/helpers.py`
- **Status**: ✅ Sudah ada

### 4.12 Generate HTML Report Interaktif
- **Deskripsi**: Render dashboard HTML standalone dengan placeholder substitution + auto-inlining CSS/JS. Mendukung paginasi 10 baris/halaman, real-time search, filter kategori, sidebar scrollspy, dan Chart.js untuk billing.
- **Entity / Data**: Template placeholder (`{{CUSTOMER_NAME}}`, `{{TOP_COST_DRIVERS}}`, `{{SERVICES_INVENTORY_CONTENT}}`, `{{SUMMARY_SERVICES}}`, dll)
- **File terkait**: `core/reporter.py` (`generate_html_report`, `_generate_services_inventory`, `_generate_summary_services`), `templates/report_template.html`, `templates/report_styles.css`, `templates/report_scripts.js`
- **Status**: ✅ Sudah ada

### 4.13 Generate PDF Report (Playwright)
- **Deskripsi**: Render PDF profesional menggunakan headless Chromium. Otomatis menonaktifkan paginasi & filter agar **semua resource** muncul dalam satu dokumen, plus header/footer dengan nomor halaman.
- **Entity / Data**: Format A4, margin 1cm, `print_background=true`
- **File terkait**: `core/reporter.py` (`generate_pdf_report`)
- **Status**: ✅ Sudah ada

### 4.14 Orchestrator Pipeline
- **Deskripsi**: Class `AWSAssessment` mewarisi `AssessmentEngine` dan menyimpan `inventory_map` (dict service_code → collector function). Eksekusi 5 tahap: Validate → Billing → Load Config → Inventory Loop → Save & Report.
- **File terkait**: `aws_assessment.py`
- **Status**: ✅ Sudah ada

---

## 5. Recommended New Features

Berikut 5 rekomendasi fitur baru yang **logis dikembangkan** berdasarkan konteks tool inventory & assessment AWS, diurutkan berdasarkan dampak bisnis:

---

### 5.1 Security Posture Scoring & Findings 🔒
**Priority: HIGH**

- **Problem**: Saat ini tool hanya melakukan **inventarisasi** (siapa & berapa), tetapi tidak mengevaluasi **kualitas** konfigurasi. Padahal data yang dikumpulkan sudah sangat dekat untuk dianalisis: ada `EBS.encrypted`, `EFS.encrypted`, `KMS.enabled`, `CloudTrail.is_multi_region`, `SecretsManager.rotation_enabled`, `S3 buckets`, dll. AWS SA & customer hampir selalu menanyakan _"Akun saya sudah aman atau belum?"_, dan tool belum bisa menjawab itu.
- **User Story**:
  - **US-001**: Sebagai AWS Solutions Architect, saya ingin melihat daftar _security findings_ di akun customer beserta skor keseluruhan, sehingga saya bisa langsung memberikan rekomendasi prioritas tanpa cek manual.
- **Functional Requirements**:
  | ID | Requirement | Priority |
  |---|---|---|
  | FR-1.1 | Modul baru `collectors/security_findings.py` yang menjalankan rule check terhadap data yang sudah ada di `assessment_data` (post-processing, tidak perlu API tambahan untuk basic checks) | High |
  | FR-1.2 | Minimal 10 rule built-in: S3 bucket public-read check, EBS unencrypted volumes, RDS unencrypted, CloudTrail tidak multi-region, KMS rotation disabled, Secrets Manager rotation disabled, IAM root MFA, default VPC masih dipakai, security group `0.0.0.0/0` untuk port sensitif, KMS key dalam state `PendingDeletion` | High |
  | FR-1.3 | Setiap finding punya struktur: `severity` (Critical/High/Medium/Low/Info), `category`, `resource_id`, `description`, `remediation` (link ke AWS docs) | High |
  | FR-1.4 | Section baru di HTML report: **Security Posture** dengan progress bar skor 0–100 dan tabel findings yang bisa di-filter per severity | High |
  | FR-1.5 | Findings juga muncul di executive summary PDF (top 5 critical) | Medium |
- **Technical Considerations**:
  - Memerlukan tambahan API call: `s3.get_bucket_acl`, `s3.get_bucket_policy_status`, `ec2.describe_security_groups`, `iam.get_account_summary`
  - Reuse field `security_findings: []` yang **sudah disiapkan di `AssessmentEngine.assessment_data`** tetapi belum dipakai → perubahan minimal
  - Skor dihitung sederhana: `100 - (Critical*15 + High*8 + Medium*3 + Low*1)`, floor 0
  - Tambah placeholder `{{SECURITY_FINDINGS}}` dan `{{SECURITY_SCORE}}` di template
  - Pertimbangkan integrasi opsional ke **AWS Security Hub** dan **GuardDuty** sebagai sumber finding yang lebih kaya (sudah ada di `services.md` tapi belum diimplementasi)
- **Breaking Changes**: Tidak ada (additive)

---

### 5.2 Cost Optimization Recommendations 💰
**Priority: HIGH**

- **Problem**: Tool sudah menampilkan billing breakdown, tetapi tidak memberi tahu _di mana customer membuang uang_. Ini adalah _signature value_ yang paling diharapkan dari assessment AWS — dan datanya sebagian besar sudah ada (EBS unattached, EC2 stopped tapi disk masih ada, NAT Gateway over-provisioned, Lambda memory belum tepat, RDS tanpa Multi-AZ, dll).
- **User Story**:
  - **US-002**: Sebagai Konsultan AWS, saya ingin tool secara otomatis menemukan resource yang boros biaya dan memberikan estimasi penghematan, sehingga laporan saya punya angka konkret yang bisa dijual.
- **Functional Requirements**:
  | ID | Requirement | Priority |
  |---|---|---|
  | FR-2.1 | Modul baru `collectors/cost_optimization.py` dengan 5 rule wajib: (a) EBS unattached, (b) EC2 stopped > 7 hari dengan EBS attached, (c) Elastic IP tidak ter-attach, (d) Snapshot orphan (volume sudah dihapus), (e) Idle Load Balancer | High |
  | FR-2.2 | Estimasi saving per finding (USD/bulan) berdasarkan price list AWS untuk region target | High |
  | FR-2.3 | Integrasi opsional dengan **AWS Trusted Advisor** API (jika customer punya Business/Enterprise Support) | Medium |
  | FR-2.4 | Section baru "💡 Cost Optimization" di HTML/PDF report dengan total potential saving di top card | High |
  | FR-2.5 | Export rekomendasi ke CSV/Excel terpisah untuk mempermudah action plan | Low |
- **Technical Considerations**:
  - API tambahan: `ec2.describe_addresses` (Elastic IP), `ec2.describe_snapshots(OwnerIds=['self'])`, `cloudwatch.get_metric_statistics` untuk deteksi idle LB
  - Price list bisa di-hardcode untuk region populer (ap-southeast-1, us-east-1) atau pakai **AWS Pricing API** (`pricing.get_products`)
  - Reuse pola `inventory_map` yang sudah ada di `aws_assessment.py` — tinggal tambah entry baru
- **Breaking Changes**: Tidak ada (additive)

---

### 5.3 Multi-Account Assessment via AWS Organizations 🏢
**Priority: HIGH**

- **Problem**: Saat ini satu run = satu akun AWS (single `.env`). Untuk customer enterprise yang punya AWS Organizations dengan 5–50 akun, konsultan harus copy-paste credential berulang kali — tidak scalable.
- **User Story**:
  - **US-003**: Sebagai MSP yang mengelola customer enterprise, saya ingin menjalankan satu kali perintah dan tool men-scan semua akun di AWS Organizations, sehingga saya bisa menghasilkan laporan konsolidasi dalam satu kali kerja.
- **Functional Requirements**:
  | ID | Requirement | Priority |
  |---|---|---|
  | FR-3.1 | Mode `--multi-account` yang membaca daftar akun dari AWS Organizations API atau dari file `accounts.yaml` | High |
  | FR-3.2 | Setiap akun di-assess via `sts:AssumeRole` ke role yang sama (mis. `OrganizationAccountAccessRole`) | High |
  | FR-3.3 | Output per-akun ditambah satu **consolidated report** (HTML + PDF) dengan ringkasan total resource lintas akun | High |
  | FR-3.4 | Eksekusi paralel (thread pool) untuk akun yang banyak, dengan rate-limit yang aman | Medium |
  | FR-3.5 | Penanganan akun yang gagal: lanjutkan akun lain & tampilkan di section "Failed Accounts" | High |
- **Technical Considerations**:
  - API tambahan: `organizations.list_accounts`, `sts.assume_role`
  - Refactor `AssessmentEngine.__init__` agar bisa menerima session dari luar (DI pattern), bukan selalu load dari `.env`
  - Tambah module `core/orchestrator_multi.py` agar logic single-account tidak terpengaruh
  - File output multi-account: `output/<account_id>/...` agar tidak tabrakan
- **Breaking Changes**: Tidak ada untuk single-account flow. Multi-account adalah opt-in via flag.

---

### 5.4 Historical Comparison & Drift Detection 📊
**Priority: MEDIUM**

- **Problem**: Setiap run menghasilkan JSON baru di `output/`, tetapi tidak pernah dibandingkan. Padahal banyak pertanyaan customer yang baru bisa dijawab kalau ada **time-series**: _"Apa saja resource baru bulan ini?"_, _"Cost growth-nya berapa?"_, _"Ada konfigurasi yang berubah tanpa saya tahu?"_.
- **User Story**:
  - **US-004**: Sebagai Cloud Engineer, saya ingin membandingkan dua hasil assessment (lama dan baru), sehingga saya bisa melihat resource yang ditambah, dihapus, atau berubah konfigurasinya.
- **Functional Requirements**:
  | ID | Requirement | Priority |
  |---|---|---|
  | FR-4.1 | Command baru `python aws_assessment.py --compare <old.json> <new.json>` | High |
  | FR-4.2 | Diff per service: `added[]`, `removed[]`, `changed[]` (untuk EC2 misalnya: tipe instance berubah, state berubah) | High |
  | FR-4.3 | Cost growth chart: bandingkan `total_actual` antar dua period | Medium |
  | FR-4.4 | Output dedicated: `output/comparison_<old>_vs_<new>.html` | Medium |
  | FR-4.5 | Highlight drift yang sensitif keamanan (mis. encryption diubah dari `true` → `false`) | High |
- **Technical Considerations**:
  - Pure post-processing, **tidak butuh API call AWS sama sekali** — hanya baca dua JSON
  - Manfaatkan struktur `assessment_data['services'][<service_key>]['<resource_list>']` yang sudah konsisten
  - Diff library: `deepdiff` (tambah ke `requirements.txt`)
  - Re-use template HTML yang ada dengan section khusus `{{COMPARISON_CONTENT}}`
- **Breaking Changes**: Tidak ada (subcommand baru)

---

### 5.5 Tag Compliance & Resource Inventory Export 🏷️
**Priority: MEDIUM**

- **Problem**: Banyak organisasi punya **tagging policy** (mis. wajib tag `Environment`, `Owner`, `CostCenter`). Saat ini tool tidak memeriksa atau menampilkan tag sama sekali. Akibatnya laporan kurang berguna untuk governance & cost allocation.
- **User Story**:
  - **US-005**: Sebagai Cloud Governance Officer, saya ingin melihat resource mana yang tidak memenuhi tagging policy dan mengekspor seluruh inventory ke Excel untuk review tim Finance.
- **Functional Requirements**:
  | ID | Requirement | Priority |
  |---|---|---|
  | FR-5.1 | Setiap collector menambahkan field `tags` (dict) ke output resource yang di-list | High |
  | FR-5.2 | File `tagging_policy.yaml` (opsional) untuk mendefinisikan required tag keys & format | Medium |
  | FR-5.3 | Section "Tag Compliance" di HTML/PDF report dengan persentase compliance per service | Medium |
  | FR-5.4 | Export tombol "Download Excel" di HTML report yang memicu generate `assessment_<timestamp>.xlsx` | Low |
  | FR-5.5 | Backward compatible: kalau `tagging_policy.yaml` tidak ada, hanya tampilkan tag tanpa scoring | High |
- **Technical Considerations**:
  - Modifikasi minor di tiap collector untuk membaca `Tags` dari response boto3 (mayoritas service AWS sudah mengembalikan tags)
  - Library tambahan: `openpyxl` untuk Excel export
  - Pertimbangkan reuse data yang dikembalikan oleh **Resource Groups Tagging API** (`resourcegroupstaggingapi.get_resources`) untuk lebih efisien
  - Update template `report_template.html` & `report_template.html` placeholder
- **Breaking Changes**: Format JSON output berubah (tambah field `tags`). Konsumen lama JSON yang strict mungkin perlu adjustment kecil.

---

## 6. Open Questions

Hal-hal yang perlu dikonfirmasi dengan tim sebelum development dimulai:

1. **Target customer utama**: tool ini lebih banyak dipakai untuk _pre-sales assessment_ (sekali pakai per customer) atau _ongoing audit_ (rutin bulanan)? Jawaban ini menentukan prioritas antara fitur **5.4 Historical Comparison** vs fitur **5.3 Multi-Account**.

2. **Cakupan keamanan**: untuk fitur **5.1 Security Findings**, apakah cukup pakai **rule built-in sederhana** (cepat, tidak perlu setup tambahan) atau wajib integrasi dengan **Security Hub** & **GuardDuty** (lebih kaya, tapi customer harus enable services tersebut yang berbayar)?

3. **Pricing data untuk fitur 5.2**: hardcode harga untuk region populer saja, atau integrasi penuh dengan **AWS Pricing API** (lebih akurat tapi menambah latency dan permission)?

4. **Format konfigurasi tagging policy (5.5)**: apakah cukup `yaml` sederhana, atau perlu compatible dengan **AWS Organizations Tag Policies** yang berbasis JSON?

5. **Format laporan tambahan**: apakah perlu dukungan **Excel (.xlsx)** dan **PowerPoint (.pptx)** untuk presentasi? Ini akan mengubah scope dependency (tambah `openpyxl`, `python-pptx`).

6. **Bahasa laporan**: saat ini campuran ID + EN. Apakah perlu fitur **i18n** untuk customer multinasional (toggle bahasa report HTML)?

7. **State management untuk multi-account**: bila fitur 5.3 jalan, di mana credential role-arn disimpan? File plain-text atau pakai **AWS SSO** / **IAM Identity Center**?

8. **Region scope**: saat ini scan hanya satu region (kecuali Cost Explorer & CloudFront WAF yang global). Apakah perlu mode `--all-regions` untuk customer yang punya resource di banyak region?

9. **Performance & rate limiting**: untuk akun besar (1000+ EC2), apakah perlu mekanisme retry/backoff yang lebih canggih dan paralelisme antar collector?

10. **Distribusi tool**: rencana ke depan tetap CLI berbasis `pip install` atau perlu kemasan **Docker image** / **standalone binary** (PyInstaller) untuk tim non-Python?

---

## Lampiran: Ringkasan Arsitektur Saat Ini

```
aws_assessment.py (Orchestrator)
    └── core/engine.py (AssessmentEngine: session + data store)
        ├── collectors/billing.py     → Cost Explorer
        ├── collectors/compute.py     → EC2, Lambda, EKS, ALB, ECR
        ├── collectors/storage.py     → S3, EBS, EFS, Backup
        ├── collectors/database.py    → RDS, DynamoDB, ElastiCache
        ├── collectors/network.py     → VPC, NAT, CloudFront, ELB, NLB, Route 53
        ├── collectors/security.py    → KMS, WAF, Secrets Manager
        ├── collectors/integration.py → SNS, MSK, MQ, Glue, CloudWatch
        └── collectors/operations.py  → CloudTrail, Config
    └── core/reporter.py (HTML + PDF via Playwright)
        └── templates/ (HTML + CSS + JS terpisah, auto-inlined)
    └── utils/
        ├── config_loader.py  → parser services.md
        └── helpers.py        → DecimalEncoder
```

**Alur eksekusi**: `validate_credentials` → `get_billing_data` → `load_services_config` → loop `inventory_map` → `save_data` → `generate_html_report` → `generate_pdf_report`.

---

> **Catatan Akhir**: Semua rekomendasi di atas dirancang **additive** dan kompatibel dengan arsitektur modular v2.0. Tidak ada rekomendasi yang memerlukan rewrite besar. Pola yang sudah baik (separation of concerns antara `engine`, `collectors`, `reporter`) bisa langsung dimanfaatkan untuk menambah modul baru.
