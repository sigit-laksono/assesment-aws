# Rencana Refaktor: AWS Assessment Tool (Modularisasi)

Dokumen ini menjelaskan rencana untuk memecah file tunggal `aws_assessment.py` yang saat ini memiliki 2200+ baris menjadi struktur yang modular agar lebih mudah dipelihara (maintainable) dan dikembangkan.

## 1. Masalah Saat Ini (Monolithic structure)
- **Hard to Maintain:** File terlalu panjang membuat navigasi dan debugging sulit.
- **Tightly Coupled:** Logika pengambilan data (AWS SDK), logika bisnis (billing), dan logika presentasi (HTML generation) bercampur di satu tempat.
- **Risk of Regression:** Perubahan kecil di satu layanan AWS berisiko merusak alur kerja layanan lain karena berada dalam class yang sama.

## 2. Arsitektur Baru yang Diusulkan

### Struktur Folder
```text
Assesment Report/
├── aws_assessment.py         # Entry point (Manager/Orchestrator)
├── core/
│   ├── __init__.py
│   ├── engine.py             # Logika inti AWS Session & Coordination
│   └── reporter.py           # Logika generate HTML & PDF
├── collectors/
│   ├── __init__.py
│   ├── compute.py            # EC2, Lambda, EKS, ALB
│   ├── storage.py            # S3, EBS, EFS, Backup
│   ├── database.py           # RDS, DynamoDB, ElastiCache
│   ├── network.py            # VPC, NAT Gateway, CloudFront
│   ├── security.py           # KMS, WAF, Secrets Manager
│   └── integration.py        # SNS, MSK, MQ, Glue, CloudWatch
├── utils/
│   ├── __init__.py
│   ├── config_loader.py      # Pengolah services.md
│   └── helpers.py            # DecimalEncoder & common helpers
└── output/                   # Folder hasil report
```

### Tanggung Jawab Modul
1. **`core/engine.py`**: Mengelola inisialisasi `boto3.session` dan menyimpan `assessment_data` yang akan dibagikan ke semua collector.
2. **`collectors/`**: Setiap file di sini hanya fokus mengambil data dari AWS API dan mengembalikannya dalam format JSON/Dictionary yang konsisten.
3. **`core/reporter.py`**: Mengambil `assessment_data` yang sudah terkumpul dan menggabungkannya ke dalam template HTML.
4. **`aws_assessment.py`**: File utama yang dijalankan user. Ia akan mengimpor modul-modul di atas dan menjalankan alur kerja (`validate -> collect -> report`).

## 3. Rencana Tahapan Kerja (Phases)

### Fase 1: Persiapan Dasar (Boilerplate)
- Membuat struktur folder dan file `__init__.py`.
- Memisahkan class `DecimalEncoder` dan helper dasar ke `utils/helpers.py`.
- Membuat base class di `core/engine.py`.

### Fase 2: Modularisasi Collector (Bertahap)
- Pindahkan fungsi `inventory_ec2`, `inventory_lambda`, dll ke `collectors/compute.py`.
- Pindahkan fungsi `inventory_s3`, `inventory_ebs`, dll ke `collectors/storage.py`.
- *Ulangi untuk semua kategori layanan.*

### Fase 3: Pemisahan Logika Pelaporan
- Memindahkan fungsi `_generate_services_inventory` dan `generate_html_report` yang sangat panjang ke `core/reporter.py`.
- Memastikan sistem penggantian template `{{TAG}}` tetap bekerja dengan baik.

### Fase 4: Integrasi & Testing
- Memperbarui `aws_assessment.py` untuk menjadi "Hub" yang memanggil semua modul baru.
- Menjalankan assessment lengkap untuk memastikan hasil akhir (file output) identik dengan versi sebelumnya.

## 4. Cara Menjalankan Setelah Refaktor
User tetap cukup menjalankan satu perintah yang sama:
```bash
python3 aws_assessment.py
```

## 5. Keuntungan Setelah Refaktor
- **Clean Code:** File utama mungkin akan turun dari 2200 baris menjadi <200 baris.
- **Scalability:** Untuk menambah layanan AWS baru, cukup buat fungsi baru di folder `collectors/`.
- **Readability:** Developer lain (atau AI) akan lebih cepat memahami struktur kode karena sudah terorganisir per domain.
