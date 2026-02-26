# AWS Account Assessment Tool

Tool untuk melakukan assessment komprehensif terhadap AWS account customer dan menghasilkan HTML report yang profesional.

## 🚀 Quick Start untuk Team

### Cara Paling Mudah: Gunakan Kiro Specs

1. **Buka Kiro IDE** dan load project ini
2. **Buka Specs Panel** (di sidebar atau command palette: "Open Specs")
3. **Pilih "AWS Account Assessment"** spec
4. **Klik "Start Task"** dan ikuti guided workflow
5. **Done!** Report akan otomatis di-generate

### Cara Alternatif: Prompting Langsung

Cukup chat dengan Kiro:
- "Jalankan assessment untuk customer saya"
- "Setup credentials untuk customer baru"
- "Buka report terakhir"
- "Berikan rekomendasi cost optimization"

Kiro akan otomatis memandu Anda step-by-step!

## Features

- ✅ Analisis billing dan cost bulan lalu
- ✅ Inventarisasi services yang digunakan (EC2, S3, RDS, Lambda, dll)
- ✅ Security assessment
- ✅ Cost optimization recommendations
- ✅ HTML report yang profesional dan mudah dibaca
- ✅ **PDF Export** - Generate report dalam format PDF
- ✅ **Pagination** - Tabel dengan pagination untuk data yang banyak
- ✅ **Summary Services** - Ringkasan semua services dengan jumlah resources
- ✅ **Status Badges** - Visual indicator untuk status resources (Running/Stopped)
- ✅ **Interactive Filters** - Filter by category, search, dan sort tables
  - Filter by Service Category (Compute, Storage, Database, dll)
  - Real-time Search untuk mencari resources spesifik
  - Sortable Tables - Click header untuk sort ascending/descending
  - Reset Filters button
- ✅ Export data ke JSON
- ✅ Auto-validation credentials dengan Hooks
- ✅ Guided workflow dengan Specs
- ✅ Integration dengan MCP AWS Documentation

## Prerequisites

- Python 3.8 atau lebih tinggi
- AWS Account dengan appropriate permissions
- Kiro IDE (recommended untuk best experience)
- AWS CLI configured (optional)

## Installation

### Untuk Team Member (Recommended)

1. **Clone repository ini**
   ```bash
   git clone <repository-url>
   cd aws-assessment-tool
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
   
   **Note untuk PDF Export:**
   Tool ini menggunakan `pdfkit` dan `wkhtmltopdf` untuk generate PDF. Anda perlu install `wkhtmltopdf` secara terpisah:
   
   - **Windows**: 
     1. Download installer dari [https://wkhtmltopdf.org/downloads.html](https://wkhtmltopdf.org/downloads.html)
     2. Install dengan default settings
     3. Restart terminal/command prompt
   
   - **macOS**: 
     ```bash
     brew install wkhtmltopdf
     ```
   
   - **Linux (Ubuntu/Debian)**: 
     ```bash
     sudo apt-get install wkhtmltopdf
     ```
   
   Jika `wkhtmltopdf` tidak terinstall, tool tetap akan berjalan dan generate HTML report (tanpa PDF).

3. **Setup credentials customer**
   ```bash
   cp .env.example .env
   ```
   
4. **Edit `.env` dengan credentials customer**
   - Buka file `.env` di Kiro IDE
   - Isi AWS credentials
   - Save file (Kiro akan auto-validate credentials via Hook!)

5. **Mulai assessment**
   - Buka Specs panel di Kiro
   - Pilih "AWS Account Assessment"
   - Klik "Start Task"
   
   ATAU chat dengan Kiro:
   ```
   "Jalankan assessment untuk customer saya"
   ```

### Manual Installation (Tanpa Kiro)

Jika tidak menggunakan Kiro IDE, ikuti langkah berikut:

1. Clone repository ini
2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Copy `.env.example` ke `.env` dan isi dengan credentials AWS:
```bash
cp .env.example .env
```

4. Edit file `.env` dengan credentials customer:
```
AWS_ACCESS_KEY_ID=your_access_key_here
AWS_SECRET_ACCESS_KEY=your_secret_key_here
AWS_REGION=ap-southeast-1
AWS_ACCOUNT_ID=123456789012
CUSTOMER_NAME=Customer Name
```

5. Jalankan assessment:
```bash
python aws_assessment.py
```

## Usage

### Dengan Kiro IDE (Recommended)

#### 1. Menggunakan Specs (Paling Mudah)
1. Buka Specs panel
2. Pilih "AWS Account Assessment"
3. Klik "Start Task"
4. Ikuti guided workflow

#### 2. Menggunakan Chat/Prompting
Cukup chat dengan Kiro menggunakan natural language:

**Setup Credentials Baru:**
```
"Setup credentials untuk customer PT. ABC"
"Ganti credentials AWS"
```

**Jalankan Assessment:**
```
"Jalankan assessment untuk customer saya"
"Lakukan full AWS assessment"
```

**View Results:**
```
"Buka report terakhir"
"Show me the latest assessment"
```

**Get Recommendations:**
```
"Berikan rekomendasi cost optimization"
"Apa yang bisa dioptimasi dari EC2?"
```

**Analyze Specific Service:**
```
"Analisis EC2 instances saja"
"Check S3 buckets"
"Lihat detail RDS databases"
```

### Manual (Tanpa Kiro)

#### Menjalankan Assessment

```bash
python aws_assessment.py
```

### Output

Assessment akan menghasilkan 2 jenis report:
- `output/assessment_data_[timestamp].json` - Data mentah dalam format JSON
- `output/assessment_report_[timestamp].html` - HTML report interaktif dengan pagination
- `output/assessment_report_[timestamp].pdf` - PDF report untuk print/share (jika WeasyPrint terinstall)

**Perbedaan HTML vs PDF:**
- **HTML Report**: Interaktif dengan pagination, sidebar navigation, dan smooth scrolling
- **PDF Report**: Print-friendly, semua data ditampilkan (tanpa pagination), cocok untuk dokumentasi dan sharing

## AWS Permissions Required

IAM user/role yang digunakan harus memiliki permissions minimal:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ce:GetCostAndUsage",
        "ec2:Describe*",
        "s3:ListAllMyBuckets",
        "s3:GetBucketLocation",
        "rds:Describe*",
        "lambda:List*",
        "lambda:Get*",
        "iam:Get*",
        "iam:List*",
        "cloudwatch:Get*",
        "cloudwatch:List*"
      ],
      "Resource": "*"
    }
  ]
}
```

## Project Structure

```
.
├── aws_assessment.py          # Main assessment script
├── templates/
│   └── report_template.html   # HTML report template
├── output/                    # Generated reports (gitignored)
├── .env                       # AWS credentials (gitignored)
├── .env.example              # Example env file
├── requirements.txt          # Python dependencies
└── README.md                 # This file
```

## Workflow

1. **Validasi Credentials** - Memastikan AWS credentials valid
2. **Billing Analysis** - Mengambil data cost bulan lalu
3. **Service Inventory** - Inventarisasi semua services yang digunakan
4. **Security Assessment** - Analisis konfigurasi keamanan
5. **Generate Recommendations** - Membuat rekomendasi optimasi
6. **Create Report** - Generate HTML report profesional

## Troubleshooting

### Error: "Cost Explorer API not enabled"
- Aktifkan Cost Explorer di AWS Console
- Tunggu 24 jam setelah aktivasi untuk data tersedia

### Error: "Access Denied"
- Pastikan IAM user/role memiliki permissions yang cukup
- Check IAM policies yang attached

### Error: "Invalid credentials"
- Verify AWS_ACCESS_KEY_ID dan AWS_SECRET_ACCESS_KEY di .env
- Pastikan credentials masih aktif

## Contributing

Silakan buat issue atau pull request untuk improvements.

## License

MIT License
