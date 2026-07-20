#!/usr/bin/env python3
"""
AWS Account Assessment Tool (Modular Version)
Melakukan analisis komprehensif terhadap AWS account dan generate HTML report.
"""

import os
import sys
from datetime import datetime

# Import Core modules
from core.engine import AssessmentEngine
from core.reporter import generate_html_report, generate_pdf_report

# Import Cost Optimization
from collectors.cost_optimization import run_cost_optimization

# Import Utils
from utils.interactive import run_interactive_setup

# Import Collectors
from collectors.billing import get_billing_data
from collectors.compute import inventory_ec2, inventory_lambda, inventory_eks, inventory_alb, inventory_ecr
from collectors.storage import inventory_s3, inventory_ebs, inventory_efs, inventory_backup
from collectors.database import inventory_rds, inventory_dynamodb, inventory_elasticache
from collectors.network import inventory_vpc, inventory_nat_gateway, inventory_cloudfront, inventory_route53, inventory_nlb
from collectors.security import inventory_kms, inventory_waf, inventory_secretsmanager, inventory_iam
from collectors.integration import inventory_sns, inventory_msk, inventory_amazonmq, inventory_glue, inventory_cloudwatch
from collectors.operations import inventory_cloudtrail, inventory_config

class AWSAssessment(AssessmentEngine):
    """
    Orchestrator untuk AWS Assessment.
    Mewarisi AssessmentEngine untuk manajemen session dan data.
    """

    def __init__(
        self,
        customer_name: str = 'AWS Customer',
        region: str = 'ap-southeast-1',
    ):
        super().__init__(
            customer_name=customer_name,
            region=region,
        )
        # Mapping service code ke fungsi kolektor
        self.inventory_map = {
            'ec2': inventory_ec2,
            's3': inventory_s3,
            'rds': inventory_rds,
            'lambda': inventory_lambda,
            'dynamodb': inventory_dynamodb,
            'cloudfront': inventory_cloudfront,
            'eks': inventory_eks,
            'ebs': inventory_ebs,
            'elasticache': inventory_elasticache,
            'vpc': inventory_vpc,
            'nat_gateway': inventory_nat_gateway,
            'iam': inventory_iam,
            'kms': inventory_kms,
            'waf': inventory_waf,
            'cloudwatch': inventory_cloudwatch,
            'cloudtrail': inventory_cloudtrail,
            'config': inventory_config,
            'efs': inventory_efs,
            'backup': inventory_backup,
            'alb': inventory_alb,
            'secretsmanager': inventory_secretsmanager,
            'sns': inventory_sns,
            'msk': inventory_msk,
            'amazonmq': inventory_amazonmq,
            'glue': inventory_glue,
            'ecr': inventory_ecr,
            'route53': inventory_route53,
            'nlb': inventory_nlb,
        }

    def run_assessment(self, selected_services: list):
        """
        Jalankan alur kerja assessment secara lengkap.
        selected_services: list service codes dari interactive setup (mis. ['ec2', 's3', 'rds']).
        """
        print("\n" + "="*60)
        print("🚀 AWS Account Assessment — dimulai")
        print("="*60)

        # 1. Validasi Credentials
        if not self.validate_credentials():
            print("\n✗ Assessment gagal: Credentials tidak valid")
            return False

        # 2. Ambil data billing (Cost Explorer)
        get_billing_data(self.session, self.assessment_data)

        # 3. Bangun daftar services dari pilihan interaktif
        services_config = {
            code: {'enabled': True, 'display_name': code.upper()}
            for code in (selected_services or [])
            if code in self.inventory_map
        }

        # 4. Inventory services
        enabled = [
            (name, cfg) for name, cfg in services_config.items()
            if cfg.get('enabled', False)
        ]
        total = len(enabled)

        print("\n" + "="*60)
        print(f"📦 Inventarisasi Services ({total} service dipilih)")
        print("="*60)

        results = {}   # {service_name: 'ok' | 'error'}
        for i, (service_name, config) in enumerate(enabled, start=1):
            label = config.get('display_name', service_name.upper())
            print(f"\n[{i}/{total}] → {label}...")
            try:
                self.inventory_map[service_name](self.session, self.assessment_data)
                results[service_name] = 'ok'
            except Exception as e:
                print(f"  ✗ Error: {str(e)}")
                results[service_name] = f'error: {str(e)}'

        # 5. Cost optimization analysis
        run_cost_optimization(self.session, self.assessment_data)

        # 6. Simpan data mentah ke JSON
        self.save_data()

        # 7. Run summary
        print("\n" + "="*60)
        print("📋 Run Summary")
        print("="*60)
        ok_count  = sum(1 for v in results.values() if v == 'ok')
        err_count = total - ok_count
        for name, status in results.items():
            icon = "✓" if status == 'ok' else "✗"
            print(f"  {icon}  {name:<20} {status}")
        print(f"\n  Total: {ok_count}/{total} berhasil"
              + (f", {err_count} gagal" if err_count else ""))
        print("="*60)

        return True

    def generate_reports(self):
        """Mendelegasikan pembuatan laporan ke modul reporter"""
        html_file = generate_html_report(
            self.assessment_data, 
            self.customer_name, 
            self.account_id, 
            self.region
        )
        
        pdf_file = generate_pdf_report(html_file)
        
        return html_file, pdf_file

def main():
    """
    Main Entry Point.
    Pemilihan services wajib lewat interactive terminal — tidak ada fallback ke file.
    """
    try:
        # ── Interactive Setup ─────────────────────────────────────────────────
        setup = run_interactive_setup()

        if setup is None:
            # User cancel (Ctrl+C) atau error di wizard
            print("\n  Assessment dibatalkan.\n")
            sys.exit(0)

        assessment = AWSAssessment(
            customer_name=setup['customer_name'],
            region=setup['region'],
        )

        # ── Assessment ────────────────────────────────────────────────────────
        if assessment.run_assessment(selected_services=setup['selected_services']):
            html_report, pdf_report = assessment.generate_reports()

            print("\n✅ Assessment selesai!")
            print(f"   HTML : {html_report}")
            if pdf_report:
                print(f"   PDF  : {pdf_report}")
        else:
            print("\n❌ Assessment gagal!")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\n  Assessment dibatalkan oleh user.\n")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error Fatal: {str(e)}")
        # import traceback; traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
