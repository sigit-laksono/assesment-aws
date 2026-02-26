import os
import re

def load_services_config(file_path='services.md'):
    """Load services configuration dari services.md"""
    
    # Mapping nama service di markdown ke nama service di code
    service_mapping = {
        'EC2 (Elastic Compute Cloud)': 'ec2',
        'Lambda': 'lambda',
        'ECS (Elastic Container Service)': 'ecs',
        'EKS (Elastic Kubernetes Service)': 'eks',
        'Fargate': 'fargate',
        'ECR (Elastic Container Registry)': 'ecr',
        'S3 (Simple Storage Service)': 's3',
        'EBS (Elastic Block Store)': 'ebs',
        'EFS (Elastic File System)': 'efs',
        'AWS Backup': 'backup',
        'RDS (Relational Database Service)': 'rds',
        'Aurora': 'aurora',
        'DynamoDB': 'dynamodb',
        'ElastiCache': 'elasticache',
        'Redshift': 'redshift',
        'VPC (Virtual Private Cloud)': 'vpc',
        'CloudFront': 'cloudfront',
        'Route 53': 'route53',
        'Direct Connect': 'directconnect',
        'Elastic Load Balancing (ELB)': 'elb',
        'Application Load Balancer (ALB)': 'alb',
        'Network Load Balancer (NLB)': 'nlb',
        'NAT Gateway': 'nat_gateway',
        'API Gateway': 'apigateway',
        'IAM (Identity and Access Management)': 'iam',
        'KMS (Key Management Service)': 'kms',
        'Secrets Manager': 'secretsmanager',
        'WAF (Web Application Firewall)': 'waf',
        'Shield': 'shield',
        'GuardDuty': 'guardduty',
        'Certificate Manager (ACM)': 'acm',
        'Cognito': 'cognito',
        'CloudWatch': 'cloudwatch',
        'CloudTrail': 'cloudtrail',
        'Config': 'config',
        'Systems Manager': 'ssm',
        'CloudFormation': 'cloudformation',
        'Organizations': 'organizations',
        'SQS (Simple Queue Service)': 'sqs',
        'SNS (Simple Notification Service)': 'sns',
        'EventBridge': 'eventbridge',
        'Step Functions': 'stepfunctions',
        'MSK (Managed Streaming for Apache Kafka)': 'msk',
        'Amazon MQ': 'amazonmq',
        'Athena': 'athena',
        'Kinesis': 'kinesis',
        'Glue': 'glue',
        'EMR (Elastic MapReduce)': 'emr',
        'QuickSight': 'quicksight',
    }
    
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Stop parsing at "Contoh Penggunaan" or "---" section
            if '## Contoh Penggunaan' in content:
                content = content.split('## Contoh Penggunaan')[0]
            elif '---\n\n##' in content:
                parts = content.split('---')
                if len(parts) > 2:
                    content = '---'.join(parts[:-1])
            
            services = {}
            
            # Parse table rows: | No | Service Name | [x] or [ ] |
            pattern = r'\|\s*\d+\s*\|\s*([^|]+?)\s*\|\s*\[([x ])\]\s*\|'
            matches = re.findall(pattern, content)
            
            for service_name, checked in matches:
                service_name = service_name.strip()
                is_enabled = checked == 'x'
                
                # Get service code name
                service_code = service_mapping.get(service_name)
                
                if service_code:
                    services[service_code] = {
                        'enabled': is_enabled,
                        'display_name': service_name
                    }
            
            enabled_count = sum(1 for s in services.values() if s['enabled'])
            print(f"✓ Loaded services config dari {file_path}: {enabled_count} services enabled")
            
            return services
        else:
            print(f"⚠ {file_path} tidak ditemukan, menggunakan default services")
            return {
                'ec2': {'enabled': True},
                's3': {'enabled': True},
                'rds': {'enabled': True},
                'lambda': {'enabled': True}
            }
    except Exception as e:
        print(f"✗ Error loading services config: {str(e)}")
        return {}
