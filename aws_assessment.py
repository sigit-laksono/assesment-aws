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

# Import Utils
from utils.config_loader import load_services_config

# Import Collectors
from collectors.billing import get_billing_data
from collectors.compute import inventory_ec2, inventory_lambda, inventory_eks, inventory_alb, inventory_ecr
from collectors.storage import inventory_s3, inventory_ebs, inventory_efs, inventory_backup
from collectors.database import inventory_rds, inventory_dynamodb, inventory_elasticache
from collectors.network import inventory_vpc, inventory_nat_gateway, inventory_cloudfront, inventory_elb, inventory_route53, inventory_nlb
from collectors.security import inventory_kms, inventory_waf, inventory_secretsmanager
from collectors.integration import inventory_sns, inventory_msk, inventory_amazonmq, inventory_glue, inventory_cloudwatch
from collectors.operations import inventory_cloudtrail, inventory_config

class AWSAssessment(AssessmentEngine):
    """
    Orchestrator untuk AWS Assessment.
    Mewarisi AssessmentEngine untuk manajemen session dan data.
    """
    
    def __init__(self):
        super().__init__()
        # Mapping service name ke fungsi kolektor
        self.inventory_map = {
            'ec2': inventory_ec2,
            's3': inventory_s3,
            'rds': inventory_rds,
            'lambda': inventory_lambda,
            'dynamodb': inventory_dynamodb,
            'cloudfront': inventory_cloudfront,
            'elb': inventory_elb,
            'eks': inventory_eks,
            'ebs': inventory_ebs,
            'elasticache': inventory_elasticache,
            'vpc': inventory_vpc,
            'nat_gateway': inventory_nat_gateway,
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

    def run_assessment(self):
        """Jalankan alur kerja assessment secara lengkap"""
        print("\n" + "="*60)
        print("🚀 Memulai AWS Account Assessment (v2.0 Modular)")
        print("="*60)
        
        # 1. Validasi Credentials
        if not self.validate_credentials():
            print("\n✗ Assessment gagal: Credentials tidak valid")
            return False
        
        # 2. Ambil data billing (Cost Explorer)
        get_billing_data(self.session, self.assessment_data)
        
        # 3. Load konfigurasi layanan yang akan di-scan
        services_config = load_services_config('services.md')
        
        # 4. Inventory services secara dinamis
        print("\n" + "="*60)
        print("📦 Inventarisasi Services")
        print("="*60)
        
        for service_name, config in services_config.items():
            if config.get('enabled', False) and service_name in self.inventory_map:
                print(f"\n→ Memproses {config.get('display_name', service_name.upper())}...")
                try:
                    collector_func = self.inventory_map[service_name]
                    collector_func(self.session, self.assessment_data)
                except Exception as e:
                    print(f"  ✗ Error pada kolektor {service_name}: {str(e)}")
            elif service_name in self.inventory_map:
                # Service ada tapi tidak di-enable di services.md
                pass

        # 5. Simpan data mentah ke JSON
        self.save_data()
        
        print("\n" + "="*60)
        print("✓ Tahap pengambilan data selesai!")
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
    """Main Entry Point"""
    try:
        # Inisialisasi orchestrator
        assessment = AWSAssessment()
        
        # Jalankan pengambilan data
        if assessment.run_assessment():
            # Generate laporan (HTML dan PDF)
            html_report, pdf_report = assessment.generate_reports()
            
            print("\n✅ Assessment completed successfully!")
            print(f"   - HTML: {html_report}")
            if pdf_report:
                print(f"   - PDF:  {pdf_report}")
        else:
            print("\n❌ Assessment failed!")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ Error Fatal: {str(e)}")
        # Tampilkan traceback jika diperlukan untuk debugging
        # import traceback; traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
