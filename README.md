# AWS Account Assessment Tool (Modular v2.0)

Tool profesional untuk melakukan assessment komprehensif terhadap akun AWS, menghasilkan laporan inventarisasi, analisis biaya (billing), dan ringkasan sumber daya dalam format HTML interaktif serta PDF.

## 🚀 Apa yang Baru di v2.0 (Refactored)

Kami telah melakukan refakturisasi besar-besaran untuk mengubah script monolitik menjadi arsitektur modular yang modern, bersih, dan mudah dikelola.

### 🌟 Fitur Unggulan
- **Modular Architecture**: Logika bisnis dipisah berdasarkan kategori (Compute, Storage, Network, dll). Menambah layanan AWS baru kini semudah menambah file di folder `collectors/`.
- **Modern PDF Engine (Playwright)**: Menggantikan engine lama (`pdfkit`/`wkhtmltopdf`) dengan **Playwright (Headless Chromium)**. 
  - ✅ Mendukung modern CSS (Flexbox, Grid, CSS Variables).
  - ✅ Mendukung rendering JavaScript (Chart.js kini muncul di PDF).
  - ✅ Tidak perlu instalasi manual biner OS yang rumit.
- **Improved UI/UX**: Interface dashboard baru dengan Sidebar dinamis, Scrollspy, dan mode cetak yang dioptimalkan.
- **Smart Reporting**: 
  - **Clean Asset Separation**: CSS dan JavaScript kini dipisah dari file HTML utama untuk memudahkan modifikasi desain dan fitur.
  - **Auto-Inlining (Standalone HTML)**: Meskipun file dipisah saat development, script akan menggabungkannya kembali secara otomatis saat generate report. Hasilnya tetap satu file HTML mandiri yang mudah dibagikan tanpa folder assets tambahan.
  - **HTML**: Interaktif dengan paginasi, pencarian real-time, dan filter kategori.
  - **PDF**: Otomatis menonaktifkan paginasi agar seluruh data (misal: ratusan EC2) muncul lengkap dalam satu dokumen tanpa tombol navigasi yang mengganggu.
- **Enhanced Data Handling**: Menggunakan `DecimalEncoder` untuk menangani tipe data finansial dari AWS secara akurat.
- **Improved Performance**: Penggunaan session AWS yang efisien dan pemisahan tahap *Inventory* dan *Reporting*.

---

## 🏗️ Struktur Proyek (Modular)

```text
.
├── aws_assessment.py      # Orchestrator (Main Entry Point)
├── core/                  # Jantung aplikasi
│   ├── engine.py          # Session management & Data storage
│   └── reporter.py        # Logic pembuatan HTML & PDF (Playwright)
├── collectors/            # Modul pengambil data per kategori
│   ├── billing.py         # Cost Explorer analysis
│   ├── compute.py         # EC2, Lambda, EKS, ALB
│   ├── storage.py         # S3, EBS, EFS, AWS Backup
│   ├── database.py        # RDS, DynamoDB, ElastiCache
│   ├── network.py         # VPC, NAT Gateway, CloudFront, ELB
│   ├── security.py        # KMS, WAF, Secrets Manager
│   ├── integration.py     # SNS, MSK, Amazon MQ, Glue
│   └── operations.py      # CloudTrail, AWS Config
├── utils/                 # Helper functions
│   ├── helpers.py         # JSON Encoders, Formatters
│   └── config_loader.py   # Loader untuk services.md
├── templates/             # UI Assets
│   ├── report_template.html   # Struktur HTML utama
│   ├── report_styles.css      # Desain Dashboard (Modern CSS Variables)
│   └── report_scripts.js      # Logika Filter, Search, Paginasi
├── output/                # Hasil assessment (JSON, HTML, PDF)
├── requirements.txt
└── .env                   # Konfigurasi credentials
```

---

## 🛠️ Instalasi & Setup

### 1. Persiapan Environment
Pindahkan ke folder project dan buat virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
```

### 2. Install Dependencies
Kami sekarang menggunakan **Playwright** untuk PDF yang lebih baik:
```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Konfigurasi
Copy `.env.example` ke `.env` dan isi data customer Anda:
```bash
cp .env.example .env
```
Isi variabel berikut: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `CUSTOMER_NAME`.

---

## 📈 Cara Menjalankan

Cukup jalankan orchestrator utama:
```bash
python3 aws_assessment.py
```

**Alur Kerja Otomatis:**
1. **Validation**: Mengecek koneksi ke AWS STS.
2. **Collection**: Mengambil data billing bulan lalu dan inventarisasi 22+ layanan AWS.
3. **Storage**: Menyimpan data mentah ke `output/*.json`.
4. **Reporting**: Menghasilkan `output/*.html` dan `output/*.pdf`.

---

## 📊 Detail Fitur Laporan

### 🔵 Interactive HTML Report
- **Paginasi**: Tabel besar (seperti EC2/EBS) dibagi per 10 baris agar tetap ringan.
- **Real-time Search**: Cari resource berdasarkan Nama, ID, atau Status secara instan.
- **Category Filter**: Filter tampilan berdasarkan kategori (Compute, Storage, dll).
- **Smooth Navigation**: Sidebar yang mengikuti posisi scroll Anda.

### 🔴 Professional PDF Report
- **Auto-Expansion**: Paginasi dimatikan secara otomatis saat pembuatan PDF agar SEMUA resource tercetak.
- **Chart Rendering**: Grafik biaya dari Chart.js dirender sempurna.
- **Print Optimized**: Menghilangkan tombol-tombol interaktif dan sidebar agar bersih saat diprint.

---

## 🔒 Security
IAM Policy minimal yang dibutuhkan tetap sama dengan versi sebelumnya (membutuhkan akses `ce:GetCostAndUsage` dan `Describe*` pada layanan terkait).

---

## 📝 Troubleshooting
- **Playwright Error**: Jika PDF gagal, pastikan Anda sudah menjalankan `playwright install chromium`.
- **Billing Data Kosong**: AWS Cost Explorer memerlukan waktu 24 jam untuk aktif setelah di-enable di console.
