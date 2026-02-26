# Interactive Filters - Dokumentasi

## Overview
Fitur Interactive Filters menambahkan kemampuan filtering, searching, dan sorting pada HTML report AWS Assessment untuk memudahkan eksplorasi data.

## Fitur yang Ditambahkan

### 1. Filter by Service Category
Dropdown filter untuk menampilkan layanan berdasarkan kategori:

**Kategori yang tersedia (sesuai services.md):**
- **All Services** - Tampilkan semua layanan
- **Compute Services** - EC2, Lambda, ECS, EKS, Fargate, ECR
- **Storage Services** - S3, EBS, EFS, AWS Backup
- **Database Services** - RDS, Aurora, DynamoDB, ElastiCache, Redshift
- **Networking & Content Delivery** - VPC, CloudFront, Route 53, Direct Connect, ELB, ALB, NLB, NAT Gateway, API Gateway
- **Security, Identity & Compliance** - IAM, KMS, Secrets Manager, WAF, Shield, GuardDuty, Certificate Manager (ACM), Cognito
- **Management & Governance** - CloudWatch, CloudTrail, Config, Systems Manager, CloudFormation, Organizations
- **Application Integration** - SQS, SNS, EventBridge, Step Functions, MSK, Amazon MQ
- **Analytics** - Athena, Kinesis, Glue, EMR, QuickSight
- **Machine Learning** - SageMaker, Rekognition, Comprehend, Lex, Polly, Bedrock
- **Developer Tools** - CodeCommit, CodeBuild, CodeDeploy, CodePipeline, Cloud9, Amplify
- **Migration & Transfer** - Database Migration Service (DMS), DataSync, Snow Family
- **Cost Management** - Cost Explorer, Budgets

**Cara Kerja:**
- Pilih kategori dari dropdown
- Hanya service yang termasuk kategori tersebut yang ditampilkan
- Service lain akan disembunyikan secara otomatis

### 2. Search Functionality
Search box dengan real-time filtering untuk mencari resources spesifik.

**Fitur Search:**
- Real-time search dengan debounce (300ms)
- Case-insensitive search
- Mencari di semua kolom tabel (nama, ID, status, dll)
- Highlight hasil pencarian dengan menyembunyikan row yang tidak match

**Contoh Penggunaan:**
- Cari "running" untuk melihat semua EC2 yang running
- Cari "i-" untuk melihat instance ID tertentu
- Cari nama bucket S3 spesifik
- Cari status "available" untuk RDS

### 3. Sort Tables
Kemampuan untuk sort setiap kolom di tabel.

**Fitur Sort:**
- Click pada header kolom untuk sort ascending
- Click lagi untuk sort descending
- Visual indicator (↑ ↓) menunjukkan sort direction
- Support untuk berbagai tipe data:
  - String (alphabetical)
  - Number (numeric)
  - Date (chronological)
- Auto-detect tipe data dari konten kolom

**Cara Kerja:**
- Click header kolom yang ingin di-sort
- Arrow up (↑) = ascending order
- Arrow down (↓) = descending order
- Click header lain untuk sort kolom berbeda

### 4. Reset Filters
Button untuk reset semua filter ke kondisi awal.

**Fungsi:**
- Reset category filter ke "All Services"
- Clear search box
- Tampilkan kembali semua resources
- Remove semua filter yang aktif

## Implementasi Teknis

### CSS Classes yang Ditambahkan
```css
.filter-controls        - Container untuk filter controls
.filter-group          - Group untuk setiap filter input
.btn-reset             - Button untuk reset filters
.sortable              - Header tabel yang bisa di-sort
.sortable.asc          - Header dengan sort ascending
.sortable.desc         - Header dengan sort descending
.filtered-hidden       - Element yang disembunyikan oleh filter
.no-results            - Message ketika tidak ada hasil
```

### JavaScript Functions

**Initialization Functions:**
- `groupElementsByCategory()` - Assign data-category attribute ke semua elemen terkait service
- `buildDynamicMenu()` - Build sidebar menu dengan data-category attributes

**Filter Functions:**
- `filterByCategory(category)` - Filter berdasarkan kategori menggunakan data-category
- `searchResources(query)` - Deep search di table rows dengan debounce
- `resetFilters()` - Reset semua filter dan sidebar
- `updateNoResultsMessage(count)` - Update pesan "no results"

**Sort Functions:**
- `sortTable(table, columnIndex, direction)` - Sort tabel berdasarkan kolom
- `makeSortable()` - Inisialisasi sortable headers

**Helper Functions:**
- `getServiceCategory(serviceName)` - Mapping service ke kategori dengan special cases
- `SERVICE_CATEGORIES` - Object mapping kategori ke services

### Key Improvements (Berdasarkan fix-bug-filtering.md)

#### 1. Data Attribute Grouping
- Setiap H3 service dan elemen di bawahnya diberi `data-category` attribute
- Grouping dilakukan saat DOMContentLoaded untuk performa optimal
- Memastikan H3, tabel, pagination, dan elemen lain diperlakukan sebagai satu kesatuan

#### 2. Sidebar Synchronization
- Link sidebar juga diberi `data-category` attribute
- Ketika filter aktif, sidebar hanya menampilkan link yang match kategori
- Menghindari kebingungan user dengan link yang mengarah ke section tersembunyi

#### 3. Deep Search in Table Rows
- Search tidak hanya di level global text, tapi iterasi sampai ke baris tabel
- Jika keyword ditemukan di baris tertentu, hanya baris itu yang ditampilkan
- Jika tidak ada baris yang match dalam satu tabel, seluruh section disembunyikan

#### 4. Special Case Handling
- ElastiCache → Database (bukan Compute)
- ELB/ALB/NLB → Networking
- EBS/EFS → Storage
- ECS/EKS/ECR → Compute
- EC2 → Compute
- Mencegah false positive dari keyword matching

## User Experience

### Workflow Umum
1. User membuka HTML report
2. Lihat filter controls di atas Services Inventory
3. Pilih kategori atau gunakan search untuk filter data
4. Click header tabel untuk sort data
5. Click "Reset Filters" untuk kembali ke view awal

### Performance
- Search menggunakan debounce 300ms untuk performa optimal
- Filter dan sort bekerja client-side (tidak perlu reload)
- Smooth transitions untuk UX yang baik

### Responsive Design
- Filter controls responsive dengan flexbox
- Mobile-friendly layout
- Touch-friendly buttons dan controls

## Browser Compatibility
- Modern browsers (Chrome, Firefox, Safari, Edge)
- ES6+ JavaScript features
- CSS Grid dan Flexbox

## Future Enhancements
Potensi improvement di masa depan:
- Multi-select category filter
- Advanced search dengan operators (AND, OR)
- Save filter preferences ke localStorage
- Export filtered data
- Custom filter presets
- Filter by cost range
- Filter by region
