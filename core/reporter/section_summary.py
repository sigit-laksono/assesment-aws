"""
Section: Summary Services Table
Tabel ringkasan jumlah resource per service di Executive Summary.
"""

_SERVICE_DISPLAY_NAMES = {
    'ec2':           'EC2 (Compute)',
    'eks':           'EKS (Kubernetes)',
    's3':            'S3 (Storage)',
    'ebs':           'EBS (Volumes)',
    'rds':           'RDS (Database)',
    'elasticache':   'ElastiCache',
    'vpc':           'VPC',
    'alb':           'ALB (Application Load Balancer)',
    'nlb':           'NLB (Network Load Balancer)',
    'nat_gateway':   'NAT Gateway',
    'waf':           'WAF',
    'cloudwatch':    'CloudWatch',
    'cloudtrail':    'CloudTrail',
    'kms':           'KMS',
    'iam':           'IAM (Identity & Access Management)',
    'secretsmanager':'Secrets Manager',
    'efs':           'EFS',
    'backup':        'AWS Backup',
    'config':        'AWS Config',
    'lambda':        'Lambda',
    'dynamodb':      'DynamoDB',
    'cloudfront':    'CloudFront',
    'sns':           'SNS',
    'msk':           'MSK',
    'amazonmq':      'Amazon MQ',
    'glue':          'AWS Glue',
    'ecr':           'ECR (Container Registry)',
    'route53':       'Route 53',
}


def generate_summary_services(assessment_data: dict) -> str:
    """Generate HTML rows untuk tabel Summary Services."""
    services_summary = []

    for service_key, service_data in assessment_data['services'].items():
        count = service_data.get('count', 0)
        if count > 0:
            display_name = _SERVICE_DISPLAY_NAMES.get(service_key, service_key.upper())
            services_summary.append({'name': display_name, 'count': count})

    services_summary.sort(key=lambda x: x['count'], reverse=True)

    if services_summary:
        return ''.join(
            f'<tr><td>{s["name"]}</td><td>{s["count"]}</td></tr>'
            for s in services_summary
        )

    return ('<tr><td colspan="2" style="text-align:center;color:var(--text-muted);">'
            'Tidak ada services yang ditemukan.</td></tr>')
