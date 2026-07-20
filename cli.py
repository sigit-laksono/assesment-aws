#!/usr/bin/env python3
"""
AWS Assessment CLI — Mode non-interaktif.

Pemakaian:
  python cli.py --all
  python cli.py --services ec2,s3,rds
  python cli.py --all --region ap-southeast-3
  python cli.py --all --output ./output/scan-juli
  python cli.py --all --customer "PT Contoh"
  python cli.py --list-services

Tanpa wizard, tanpa prompt. Cocok untuk automation dan AI agent.
"""

import argparse
import sys

from aws_assessment import AWSAssessment


ALL_SERVICES = [
    "ec2", "s3", "rds", "lambda", "dynamodb", "cloudfront", "eks",
    "ebs", "elasticache", "vpc", "nat_gateway", "iam", "kms", "waf",
    "cloudwatch", "cloudtrail", "config", "efs", "backup", "alb",
    "secretsmanager", "sns", "msk", "amazonmq", "glue", "ecr",
    "route53", "nlb",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="aws-assess",
        description="AWS Account Assessment — mode non-interaktif",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--all",
        action="store_true",
        help="Scan semua service yang tersedia",
    )
    group.add_argument(
        "--services",
        type=str,
        help="Comma-separated list service codes (contoh: ec2,s3,rds)",
    )
    group.add_argument(
        "--list-services",
        action="store_true",
        help="Tampilkan daftar service codes yang tersedia",
    )

    parser.add_argument(
        "--region",
        type=str,
        default="ap-southeast-1",
        help="AWS region (default: ap-southeast-1)",
    )
    parser.add_argument(
        "--customer",
        type=str,
        default="AWS Customer",
        help="Nama customer untuk report (default: AWS Customer)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Custom output directory (default: ./output/)",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Skip pembuatan HTML/PDF report, hanya simpan JSON",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # --list-services: tampilkan lalu keluar
    if args.list_services:
        print("Service codes yang tersedia:")
        for svc in sorted(ALL_SERVICES):
            print(f"  - {svc}")
        print(f"\nTotal: {len(ALL_SERVICES)} services")
        sys.exit(0)

    # Tentukan services
    if args.all:
        selected = ALL_SERVICES
    else:
        selected = [s.strip() for s in args.services.split(",") if s.strip()]
        invalid = [s for s in selected if s not in ALL_SERVICES]
        if invalid:
            print(f"✗ Service tidak dikenal: {invalid}")
            print(f"  Gunakan --list-services untuk melihat yang tersedia.")
            sys.exit(1)

    # Override output directory jika diminta
    if args.output:
        import os
        os.makedirs(args.output, exist_ok=True)
        # Patch output path di save_data nanti
        os.environ["AWS_ASSESS_OUTPUT_DIR"] = args.output

    # Jalankan assessment
    assessment = AWSAssessment(
        customer_name=args.customer,
        region=args.region,
    )

    if not assessment.run_assessment(selected_services=selected):
        print("\n✗ Assessment gagal!")
        sys.exit(1)

    # Generate report kecuali --no-report
    if not args.no_report:
        html_report = assessment.generate_reports()
        print(f"\n✅ Assessment selesai!")
        print(f"   HTML : {html_report}")
    else:
        print(f"\n✅ Assessment selesai (JSON only, report dilewati)")


if __name__ == "__main__":
    main()
