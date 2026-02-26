# Dokumentasi AWS Assessment Tool

## Daftar Isi
1. [Overview](#overview)
2. [Arsitektur Sistem](#arsitektur-sistem)
3. [Flow Eksekusi](#flow-eksekusi)
4. [Komponen Utama](#komponen-utama)
5. [Cara Kerja Detail](#cara-kerja-detail)
6. [Konfigurasi Services](#konfigurasi-services)
7. [Output yang Dihasilkan](#output-yang-dihasilkan)

---

## Overview

AWS Assessment Tool adalah script Python yang melakukan analisis komprehensif terhadap AWS account Anda. Tool ini mengumpulkan informasi tentang resources yang digunakan, biaya, dan menghasilkan laporan dalam format HTML dan PDF.

### Tujuan Utama
- Inventarisasi semua AWS resources yang aktif
- Analisis biaya per service
- Generate laporan visual yang mudah dipahami
- Memberikan rekomendasi optimasi

---

## Arsitektur Sistem

```
┌─────────────────────────────────────────────────────────┐
│                   AWS Assessment Tool                    │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────────┐      ┌──────────────┐                │
│  │   .env File  │─────▶│ Credentials  │                │
│  └──────────────┘      └──────────────┘                │
│                              │                           │
│                              ▼                           │
│  ┌──────────────┐      ┌──────────────┐                │
│  │services.md   │─────▶│ AWS Session  │                │
│  │(Config)      │      │   (boto3)    │                │
│  └──────────────┘      └──────────────┘                │
│                              │                           │
│                              ▼                           │
│                    ┌──────────────────┐                 │
│                    │  Data Collection │                 │
│                    │   (Inventory)    │                 │
│                    └──────────────────┘                 │
│                              │                           │
│                    ┌─────────┴─────────┐                │
│                    ▼                   ▼                │
│            ┌──────────────┐    ┌──────────────┐        │
│            │ Billing Data │    │Service Data  │        │
│            │(Cost Explorer)│    │(EC2,S3,RDS,..)│       │
│            └──────────────┘    └──────────────┘        │
│                    │                   │                │
│                    └─────────┬─────────┘                │
│                              ▼                           │
│                    ┌──────────────────┐                 │
│                    │  Generate Report │                 │
│                    │   (HTML + PDF)   │                 │
│                    └──────────────────┘                 │
│                              │                           │
│                              ▼                           │
│                    ┌──────────────────┐                 │
│                    │  Output Files    │                 │
│                    │  - JSON          │                 │
│                    │  - HTML          │                 │
│                    │  - PDF           │                 │
│                    └──────────────────┘                 │
└─────────────────────────────────────────────────────────┘
```

---

## Flow Eksekusi

### 1. Initialization Phase
```python
assessment = AWSAssessment()
```

**Yang Terjadi:**
- Load environment variables dari `.env` file
- Validasi AWS credentials (Access Key & Secret Key)
- Inisialisasi boto3 session dengan credentials
- Setup data storage structure

**File yang Digunakan:**
- `.env` - Berisi AWS credentials dan konfigurasi

### 2. Validation Phase
```python
assessment.validate_credentials()
```

**Yang Terjadi:**
- Memanggil AWS STS (Security Token Service)
- Verifikasi credentials valid
- Mendapatkan Account ID
- Mendapatkan User ARN

**AWS API yang Dipanggil:**
- `sts.get_caller_identity()`

### 3. Billing Data Collection
```python
assessment.get_billing_data()
```

**Yang Terjadi:**
- Connect ke AWS Cost Explorer (region us-east-1)
- Ambil data biaya bulan lalu
- Breakdown biaya per service
- Identifikasi top 10 services dengan biaya tertinggi

**AWS API yang Dipanggil:**
- `ce.get_cost_and_usage()` - Total cost
- `ce.get_cost_and_usage(GroupBy=['SERVICE'])` - Cost per service

**Data yang Dikumpulkan:**
```json
{
  "monthly_costs": [
    {
      "period": "2024-01-01",
      "total": 1234.56
    }
  ],
  "service_costs": {
    "Amazon EC2": [
      {"period": "2024-01-01", "cost": 500.00}
    ]
  },
  "top_services": [
    ["Amazon EC2", 500.00],
    ["Amazon S3", 200.00]
  ]
}
```

### 4. Services Configuration Loading
```python
services_config = assessment.load_services_config()
```

**Yang Terjadi:**
- Baca file `services.md`
- Parse tabel markdown untuk melihat service mana yang enabled
- Mapping nama service ke function inventory

**Format services.md:**
```markdown
| No | Service Name | Enabled |
|----|--------------|---------|
| 1  | EC2          | [x]     |
| 2  | S3           | [x]     |
| 3  | Lambda       | [ ]     |
```

### 5. Service Inventory Phase
```python
# Untuk setiap service yang enabled
assessment.inventory_ec2()
assessment.inventory_s3()
assessment.inventory_rds()
# ... dst
```

**Yang Terjadi untuk Setiap Service:**

#### Contoh: EC2 Inventory
```python
def inventory_ec2(self):
    ec2 = self.session.client('ec2')
    instances = ec2.describe_instances()
    
    # Parse response
    for reservation in instances['Reservations']:
        for instance in reservation['Instances']:
            # Extract data yang dibutuhkan
            instance_data = {
                'id': instance['InstanceId'],
                'type': instance['InstanceType'],
                'state': instance['State']['Name'],
                'launch_time': instance['LaunchTime']
            }
    
    # Simpan ke assessment_data
    self.assessment_data['services']['ec2'] = {
        'count': len(instance_list),
        'instances': instance_list
    }
```

**AWS API yang Dipanggil per Service:**
- EC2: `ec2.describe_instances()`
- S3: `s3.list_buckets()`
- RDS: `rds.describe_db_instances()`
- Lambda: `lambda.list_functions()`
- DynamoDB: `dynamodb.list_tables()`, `dynamodb.describe_table()`
- CloudFront: `cloudfront.list_distributions()`
- ELB: `elbv2.describe_load_balancers()`
- EKS: `eks.list_clusters()`, `eks.describe_cluster()`
- EBS: `ec2.describe_volumes()`
- ElastiCache: `elasticache.describe_cache_clusters()`
- VPC: `ec2.describe_vpcs()`
- NAT Gateway: `ec2.describe_nat_gateways()`
- KMS: `kms.list_keys()`, `kms.describe_key()`
- WAF: `wafv2.list_web_acls()`
- CloudWatch: `cloudwatch.describe_alarms()`
- CloudTrail: `cloudtrail.describe_trails()`
- Config: `config.describe_configuration_recorders()`
- EFS: `efs.describe_file_systems()`
- Backup: `backup.list_backup_vaults()`, `backup.list_backup_plans()`
- ALB: `elbv2.describe_load_balancers()` (filtered by type)
- Secrets Manager: `secretsmanager.list_secrets()`
- SNS: `sns.list_topics()`
- MSK: `kafka.list_clusters_v2()`
- Amazon MQ: `mq.list_brokers()`
- Glue: `glue.get_databases()`, `glue.get_jobs()`

### 6. Data Persistence
```python
assessment.save_assessment_data()
```

**Yang Terjadi:**
- Serialize semua data ke JSON
- Save ke file `output/assessment_data_TIMESTAMP.json`

**Format Output JSON:**
```json
{
  "customer_name": "PT Example",
  "account_id": "123456789012",
  "region": "ap-southeast-1",
  "assessment_date": "2024-01-15 10:30:00",
  "billing_data": { ... },
  "services": {
    "ec2": { ... },
    "s3": { ... }
  },
  "security_findings": []
}
```

### 7. HTML Report Generation
```python
html_file = assessment.generate_html_report()
```

**Yang Terjadi:**
- Load template dari `templates/report_template.html`
- Replace placeholders dengan data aktual
- Generate dynamic tables untuk setiap service
- Save ke `output/assessment_report_TIMESTAMP.html`

**Placeholders yang Diganti:**
- `{{CUSTOMER_NAME}}` → Nama customer dari .env
- `{{ACCOUNT_ID}}` → AWS Account ID
- `{{ASSESSMENT_DATE}}` → Tanggal assessment
- `{{SERVICES_COUNT}}` → Jumlah services yang ditemukan
- `{{RESOURCES_COUNT}}` → Total resources
- `{{TOTAL_MONTHLY_COST}}` → Total biaya bulan lalu
- `{{TOP_COST_DRIVERS}}` → Tabel top 10 services dengan biaya tertinggi
- `{{SUMMARY_SERVICES}}` → Tabel summary semua services
- `{{SERVICES_INVENTORY_CONTENT}}` → Detail inventory per service

### 8. PDF Report Generation
```python
assessment.generate_pdf_report(html_file)
```

**Yang Terjadi:**
- Gunakan pdfkit (wrapper untuk wkhtmltopdf)
- Convert HTML ke PDF dengan styling yang sama
- Save ke `output/assessment_report_TIMESTAMP.pdf`

**Requirements:**
- Python package: `pdfkit`
- System binary: `wkhtmltopdf`

---

## Komponen Utama

### 1. Class AWSAssessment

**Attributes:**
```python
self.access_key        # AWS Access Key dari .env
self.secret_key        # AWS Secret Key dari .env
self.region            # AWS Region (default: ap-southeast-1)
self.account_id        # AWS Account ID
self.customer_name     # Nama customer dari .env
self.session           # boto3 Session object
self.assessment_data   # Dictionary untuk menyimpan semua data
```

**Main Methods:**
```python
__init__()                    # Initialize assessment
validate_credentials()        # Validasi AWS credentials
get_billing_data()           # Ambil data billing
inventory_<service>()        # Inventory specific service
load_services_config()       # Load config dari services.md
run_assessment()             # Main orchestrator
generate_recommendations()   # Generate rekomendasi
save_assessment_data()       # Save data ke JSON
generate_html_report()       # Generate HTML report
generate_pdf_report()        # Generate PDF report
```

### 2. Helper Class: DecimalEncoder

**Tujuan:** Handle Decimal objects dari DynamoDB saat JSON serialization

```python
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)
```

### 3. Data Structure

**assessment_data Dictionary:**
```python
{
    'customer_name': str,
    'account_id': str,
    'region': str,
    'assessment_date': str,
    'billing_data': {
        'monthly_costs': list,
        'service_costs': dict,
        'top_services': list,
        'period': str,
        'total_actual': float
    },
    'services': {
        'ec2': {
            'count': int,
            'instances': list
        },
        's3': {
            'count': int,
            'buckets': list
        },
        # ... service lainnya
    },
    'security_findings': list,
    'recommendations': list
}
```

---

## Cara Kerja Detail

### Billing Data Collection

**Step-by-step:**

1. **Connect ke Cost Explorer**
   ```python
   ce = self.session.client('ce', region_name='us-east-1')
   ```
   Note: Cost Explorer hanya tersedia di us-east-1

2. **Calculate Date Range**
   ```python
   end_date = datetime.now().date().replace(day=1)  # Awal bulan ini
   start_date = (end_date - timedelta(days=1)).replace(day=1)  # Awal bulan lalu
   ```
   Contoh: Jika sekarang 15 Januari 2024
   - end_date = 1 Januari 2024
   - start_date = 1 Desember 2023

3. **Get Total Cost**
   ```python
   response_total = ce.get_cost_and_usage(
       TimePeriod={'Start': '2023-12-01', 'End': '2024-01-01'},
       Granularity='MONTHLY',
       Metrics=['UnblendedCost', 'BlendedCost']
   )
   ```

4. **Get Cost by Service**
   ```python
   response = ce.get_cost_and_usage(
       TimePeriod={'Start': '2023-12-01', 'End': '2024-01-01'},
       Granularity='MONTHLY',
       Metrics=['UnblendedCost'],
       GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}]
   )
   ```

5. **Process Response**
   ```python
   for result in response['ResultsByTime']:
       for group in result['Groups']:
           service = group['Keys'][0]  # Nama service
           cost = float(group['Metrics']['UnblendedCost']['Amount'])
           # Simpan ke service_costs
   ```

6. **Calculate Top Services**
   ```python
   total_by_service = {}
   for service, costs in service_costs.items():
       total_by_service[service] = sum(c['cost'] for c in costs)
   
   top_services = sorted(total_by_service.items(), 
                        key=lambda x: x[1], 
                        reverse=True)[:10]
   ```

### Service Inventory Pattern

Semua inventory functions mengikuti pattern yang sama:

```python
def inventory_<service>(self):
    print(f"\n🔍 Inventarisasi {service}...")
    
    try:
        # 1. Create service client
        client = self.session.client('<service_name>')
        
        # 2. Call AWS API
        response = client.list_<resources>()
        
        # 3. Parse response
        resource_list = []
        for item in response['<ResourceKey>']:
            resource_list.append({
                'id': item['<IdKey>'],
                'name': item.get('<NameKey>', 'N/A'),
                # ... field lainnya
            })
        
        # 4. Save to assessment_data
        self.assessment_data['services']['<service>'] = {
            'count': len(resource_list),
            '<resources>': resource_list
        }
        
        print(f"✓ Found {len(resource_list)} resources")
        return True
        
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        return False
```

### HTML Report Generation

**Step-by-step:**

1. **Load Template**
   ```python
   with open('templates/report_template.html', 'r', encoding='utf-8') as f:
       template = f.read()
   ```

2. **Calculate Summary Stats**
   ```python
   total_services = len([k for k, v in services.items() if v.get('count', 0) > 0])
   total_resources = sum(v.get('count', 0) for v in services.values())
   total_monthly_cost = billing_data['monthly_costs'][-1]['total']
   ```

3. **Replace Basic Placeholders**
   ```python
   replacements = {
       '{{CUSTOMER_NAME}}': self.customer_name,
       '{{ACCOUNT_ID}}': self.account_id,
       # ... dst
   }
   
   for placeholder, value in replacements.items():
       template = template.replace(placeholder, value)
   ```

4. **Generate Dynamic Tables**
   ```python
   # Top Cost Drivers
   top_drivers_html = ''
   for service, cost in top_services:
       percentage = (cost / total_monthly_cost * 100)
       top_drivers_html += f'''
       <tr>
           <td>{service}</td>
           <td>${cost:,.2f}</td>
           <td>{percentage:.1f}%</td>
       </tr>
       '''
   template = template.replace('{{TOP_COST_DRIVERS}}', top_drivers_html)
   ```

5. **Generate Services Inventory**
   ```python
   services_html = self._generate_services_inventory()
   template = template.replace('{{SERVICES_INVENTORY_CONTENT}}', services_html)
   ```

6. **Save HTML File**
   ```python
   timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
   output_file = f"output/assessment_report_{timestamp}.html"
   
   with open(output_file, 'w', encoding='utf-8') as f:
       f.write(template)
   ```

---

## Konfigurasi Services

### File: services.md

Format tabel markdown untuk enable/disable services:

```markdown
| No | Service Name | Enabled |
|----|--------------|---------|
| 1  | EC2          | [x]     |  ← Enabled
| 2  | S3           | [x]     |  ← Enabled
| 3  | Lambda       | [ ]     |  ← Disabled
```

### Service Mapping

```python
service_mapping = {
    'EC2 (Elastic Compute Cloud)': 'ec2',
    'Lambda': 'lambda',
    'S3 (Simple Storage Service)': 's3',
    # ... dst
}
```

### Inventory Functions Mapping

```python
inventory_functions = {
    'ec2': self.inventory_ec2,
    's3': self.inventory_s3,
    'rds': self.inventory_rds,
    # ... dst
}
```

### Execution Logic

```python
for service_name, service_config in services_config.items():
    if service_config.get('enabled', False):
        if service_name in inventory_functions:
            inventory_functions[service_name]()
```

---

## Output yang Dihasilkan

### 1. JSON Data File

**Filename:** `output/assessment_data_YYYYMMDD_HHMMSS.json`

**Content:**
```json
{
  "customer_name": "PT Example",
  "account_id": "123456789012",
  "region": "ap-southeast-1",
  "assessment_date": "2024-01-15 10:30:00",
  "billing_data": {
    "monthly_costs": [...],
    "service_costs": {...},
    "top_services": [...],
    "period": "Bulan Lalu: December 2023",
    "total_actual": 1234.56
  },
  "services": {
    "ec2": {
      "count": 5,
      "instances": [...]
    },
    "s3": {
      "count": 10,
      "buckets": [...]
    }
  },
  "security_findings": [],
  "recommendations": [...]
}
```

### 2. HTML Report

**Filename:** `output/assessment_report_YYYYMMDD_HHMMSS.html`

**Sections:**
1. **Executive Summary**
   - Customer name & Account ID
   - Total services & resources
   - Total monthly cost

2. **Cost Analysis**
   - Top 10 cost drivers
   - Breakdown per service

3. **Services Summary**
   - List semua services dengan count

4. **Detailed Inventory**
   - EC2 instances dengan pagination
   - S3 buckets
   - RDS instances
   - Lambda functions
   - DynamoDB tables
   - CloudFront distributions
   - Load Balancers
   - EKS clusters
   - EBS volumes
   - ElastiCache clusters
   - VPCs
   - NAT Gateways
   - KMS keys
   - WAF Web ACLs
   - CloudWatch alarms
   - CloudTrail trails
   - AWS Config recorders
   - EFS file systems
   - AWS Backup vaults & plans
   - ALB load balancers
   - Secrets Manager secrets
   - SNS topics
   - MSK clusters
   - Amazon MQ brokers
   - AWS Glue databases & jobs

### 3. PDF Report

**Filename:** `output/assessment_report_YYYYMMDD_HHMMSS.pdf`

**Features:**
- Same content as HTML
- Professional formatting
- Page numbers
- Headers & footers
- A4 size, portrait orientation

---

## Error Handling

### Credentials Validation
```python
try:
    sts = self.session.client('sts')
    identity = sts.get_caller_identity()
    return True
except Exception as e:
    print(f"✗ Error validating credentials: {str(e)}")
    return False
```

### Service Inventory
```python
try:
    # Inventory logic
    return True
except Exception as e:
    print(f"✗ Error inventorying {service}: {str(e)}")
    return False
```

### PDF Generation
```python
try:
    pdfkit.from_file(html_file, pdf_file, options=options)
    return pdf_file
except ImportError:
    print("⚠ pdfkit tidak terinstall")
    return None
except OSError as e:
    print("⚠ wkhtmltopdf tidak ditemukan")
    return None
```

---

## Best Practices

### 1. Credentials Management
- Gunakan `.env` file untuk credentials
- Jangan commit `.env` ke git
- Gunakan IAM user dengan permissions minimal yang dibutuhkan

### 2. Cost Explorer
- Aktifkan Cost Explorer di AWS Console
- Tunggu 24 jam setelah aktivasi untuk data pertama
- Data billing update setiap 24 jam

### 3. Permissions Required
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ce:GetCostAndUsage",
        "ec2:Describe*",
        "s3:List*",
        "rds:Describe*",
        "lambda:List*",
        "dynamodb:List*",
        "dynamodb:Describe*",
        "cloudfront:List*",
        "elasticloadbalancing:Describe*",
        "eks:List*",
        "eks:Describe*",
        "elasticache:Describe*",
        "kms:List*",
        "kms:Describe*",
        "wafv2:List*",
        "cloudwatch:Describe*",
        "cloudtrail:Describe*",
        "config:Describe*",
        "elasticfilesystem:Describe*",
        "backup:List*",
        "secretsmanager:List*",
        "sns:List*",
        "sns:GetTopicAttributes",
        "kafka:List*",
        "mq:List*",
        "glue:Get*"
      ],
      "Resource": "*"
    }
  ]
}
```

### 4. Performance
- Script berjalan sekitar 2-5 menit tergantung jumlah resources
- Gunakan services.md untuk disable services yang tidak perlu
- Pagination otomatis untuk tabel besar di HTML report

---

## Troubleshooting

### Issue: "Credentials tidak valid"
**Solution:**
- Cek `.env` file
- Pastikan AWS_ACCESS_KEY_ID dan AWS_SECRET_ACCESS_KEY benar
- Test credentials dengan AWS CLI: `aws sts get-caller-identity`

### Issue: "Cost Explorer data tidak tersedia"
**Solution:**
- Aktifkan Cost Explorer di AWS Console
- Tunggu 24 jam untuk data pertama
- Pastikan IAM user punya permission `ce:GetCostAndUsage`

### Issue: "PDF tidak ter-generate"
**Solution:**
- Install pdfkit: `pip install pdfkit`
- Install wkhtmltopdf:
  - Windows: Download dari https://wkhtmltopdf.org/downloads.html
  - macOS: `brew install wkhtmltopdf`
  - Linux: `sudo apt-get install wkhtmltopdf`
- Tambahkan wkhtmltopdf ke PATH

### Issue: "Service inventory error"
**Solution:**
- Cek IAM permissions untuk service tersebut
- Pastikan service tersebut ada resources di region yang dipilih
- Lihat error message detail di console

---

## Kesimpulan

AWS Assessment Tool adalah script yang powerful untuk:
1. ✅ Inventarisasi lengkap AWS resources
2. ✅ Analisis biaya per service
3. ✅ Generate laporan visual profesional
4. ✅ Konfigurasi flexible via services.md
5. ✅ Output dalam 3 format (JSON, HTML, PDF)

Script ini sangat berguna untuk:
- AWS Solutions Architects
- Cloud Engineers
- DevOps Teams
- Management untuk cost review
- Audit dan compliance

---

**Dibuat oleh:** AWS Assessment Tool
**Versi:** 1.0
**Tanggal:** 2024
