# Graph Report - .  (2026-07-19)

## Corpus Check
- Corpus is ~18,029 words - fits in a single context window. You may not need a graph.

## Summary
- 242 nodes · 393 edges · 15 communities (13 shown, 2 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 40 edges (avg confidence: 0.8)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Billing & Data Collection
- Compute Inventory
- Cost Optimization Engine
- Product Requirements
- HTML Report Generation
- Report UI Scripts
- Interactive CLI Utils
- Assessment Engine Core
- Main Orchestrator
- Property-Based Testing
- Test Framework

## God Nodes (most connected - your core abstractions)
1. `run_cost_optimization()` - 14 edges
2. `inventory_ec2()` - 11 edges
3. `_make_assessment_data()` - 11 edges
4. `_make_mock_session()` - 11 edges
5. `PRD AWS Assessment Tool` - 10 edges
6. `run_interactive_setup()` - 9 edges
7. `inventory_alb()` - 8 edges
8. `generate_html_report()` - 8 edges
9. `TestEC2EdgeCases` - 8 edges
10. `AWSAssessment` - 7 edges

## Surprising Connections (you probably didn't know these)
- `Auto-Inlining Standalone HTML` --semantically_similar_to--> `HTML Report Generation`  [INFERRED] [semantically similar]
  README.md → docs/PRD_AWS_Assessment_Tool.md
- `Cost Optimization Report Section` --semantically_similar_to--> `Cost Optimization Detection (6 Rules)`  [INFERRED] [semantically similar]
  templates/report_template.html → docs/PRD_AWS_Assessment_Tool.md
- `AWSAssessment` --uses--> `AssessmentEngine`  [INFERRED]
  aws_assessment.py → core/engine.py
- `main()` --calls--> `run_interactive_setup()`  [EXTRACTED]
  aws_assessment.py → utils/interactive.py
- `AssessmentEngine` --uses--> `DecimalEncoder`  [INFERRED]
  core/engine.py → utils/helpers.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Assessment Pipeline (Validate → Collect → Optimize → Report)** — docs_prd_aws_assessment_tool_orchestrator_pipeline, docs_prd_aws_assessment_tool_credential_session_management, docs_prd_aws_assessment_tool_billing_data_collection, docs_prd_aws_assessment_tool_cost_optimization, docs_prd_aws_assessment_tool_html_report, docs_prd_aws_assessment_tool_pdf_report [EXTRACTED 1.00]
- **Report Generation System (Template + HTML + PDF)** — templates_report_template, docs_prd_aws_assessment_tool_html_report, docs_prd_aws_assessment_tool_pdf_report, readme_auto_inlining, requirements_playwright [EXTRACTED 1.00]
- **Cost Analysis Subsystem (Billing + Optimization + Pricing)** — docs_prd_aws_assessment_tool_billing_data_collection, docs_prd_aws_assessment_tool_cost_optimization, docs_prd_aws_assessment_tool_pricing_engine, templates_report_template_cost_optimization_section [EXTRACTED 1.00]

## Communities (15 total, 2 thin omitted)

### Community 0 - "Billing & Data Collection"
Cohesion: 0.06
Nodes (50): get_billing_data(), Ambil data billing satu bulan terakhir dari Cost Explorer, inventory_ecr(), inventory_eks(), inventory_lambda(), Inventory ECR repositories, Inventory Lambda functions, Inventory EKS clusters (+42 more)

### Community 1 - "Compute Inventory"
Cohesion: 0.09
Nodes (28): inventory_alb(), inventory_ec2(), Inventory Application Load Balancers (ALB), Inventory EC2 instances, ec2_instance_strategy(), _make_assessment_data(), _make_mock_session(), Property-based tests for collectors/compute.py Feature: compute-collector-enhan (+20 more)

### Community 2 - "Cost Optimization Engine"
Cohesion: 0.08
Nodes (37): _ebs_monthly_cost(), _get_instance_family(), Cost Optimization Collector ============================ Mendeteksi resource yan, Flag ALB/NLB tanpa target group atau tanpa target aktif., Extract family from instance type, e.g. 'c5.2xlarge' → 'c5'., Flag Linux x86_64 instances yang bisa migrasi ke Graviton., Flag instance yang punya Public IPv4 (charged sejak Feb 2024)., Flag S3 buckets yang tidak punya lifecycle rule. (+29 more)

### Community 3 - "Product Requirements"
Cohesion: 0.09
Nodes (27): PRD AWS Assessment Tool, Billing Data Collection (Cost Explorer), Cost Optimization Detection (6 Rules), Credential & Session Management, Historical Comparison & Drift Detection (Proposed 5.3), HTML Report Generation, IAM Inventory (Summary Level), Rationale: Modular Architecture for Maintainability (+19 more)

### Community 4 - "HTML Report Generation"
Cohesion: 0.13
Nodes (16): generate_html_report(), HTML Report Generator Orchestrator yang merakit semua section menjadi satu file, Generate HTML report dari template dan kembalikan path file output., core/reporter — public API Import dari sini agar caller tidak perlu tahu struktu, generate_pdf_report(), PDF Report Generator Render HTML report ke PDF menggunakan Playwright headless C, Generate PDF dari file HTML. Return path PDF atau None jika gagal., generate_cost_optimization() (+8 more)

### Community 5 - "Report UI Scripts"
Cohesion: 0.27
Nodes (13): buildDynamicMenu(), createDots(), filterByCategory(), getServiceCategory(), makeSortable(), paginationStates, renderPaginationLinks(), resetFilters() (+5 more)

### Community 6 - "Interactive CLI Utils"
Cohesion: 0.20
Nodes (13): _build_service_table(), _confirm(), _mask(), _print_service_table(), _prompt(), Interactive setup wizard untuk AWS Assessment Tool. Menggunakan input() standar, Cetak tabel service dengan marker [x]/[ ]., Jalankan interactive setup wizard di terminal.      Return dict:         { (+5 more)

### Community 7 - "Assessment Engine Core"
Cohesion: 0.21
Nodes (6): AssessmentEngine, Initialize AWS Assessment.          Nilai bisa datang dari 2 sumber (prioritas a, Validasi AWS credentials dan permissions, Save assessment data ke JSON file, DecimalEncoder, Helper untuk encode Decimal ke JSON

### Community 8 - "Main Orchestrator"
Cohesion: 0.32
Nodes (6): AWSAssessment, main(), Mendelegasikan pembuatan laporan ke modul reporter, Main Entry Point.     Pemilihan services wajib lewat interactive terminal — tid, Orchestrator untuk AWS Assessment.     Mewarisi AssessmentEngine untuk manajeme, Jalankan alur kerja assessment secara lengkap.         selected_services: list

## Knowledge Gaps
- **11 isolated node(s):** `paginationStates`, `Services.md Checklist Configuration`, `Billing Data Collection (Cost Explorer)`, `Multi-Account Assessment (Proposed 5.2)`, `Historical Comparison & Drift Detection (Proposed 5.3)` (+6 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `inventory_ec2()` connect `Compute Inventory` to `Billing & Data Collection`?**
  _High betweenness centrality (0.120) - this node is a cross-community bridge._
- **Why does `generate_html_report()` connect `HTML Report Generation` to `Billing & Data Collection`, `Main Orchestrator`?**
  _High betweenness centrality (0.099) - this node is a cross-community bridge._
- **Why does `inventory_alb()` connect `Compute Inventory` to `Billing & Data Collection`?**
  _High betweenness centrality (0.085) - this node is a cross-community bridge._
- **What connects `paginationStates`, `Services.md Checklist Configuration`, `Billing Data Collection (Cost Explorer)` to the rest of the system?**
  _11 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Billing & Data Collection` be split into smaller, more focused modules?**
  _Cohesion score 0.06253652834599649 - nodes in this community are weakly interconnected._
- **Should `Compute Inventory` be split into smaller, more focused modules?**
  _Cohesion score 0.09230769230769231 - nodes in this community are weakly interconnected._
- **Should `Cost Optimization Engine` be split into smaller, more focused modules?**
  _Cohesion score 0.08076923076923077 - nodes in this community are weakly interconnected._