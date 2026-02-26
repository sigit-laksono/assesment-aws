#!/usr/bin/env python3
"""
AWS Account Assessment Tool
Melakukan analisis komprehensif terhadap AWS account dan generate HTML report
"""

import boto3
import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from decimal import Decimal
import sys

class DecimalEncoder(json.JSONEncoder):
    """Helper untuk encode Decimal ke JSON"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

class AWSAssessment:
    def __init__(self):
        """Initialize AWS Assessment dengan credentials dari .env"""
        load_dotenv()
        
        self.access_key = os.getenv('AWS_ACCESS_KEY_ID')
        self.secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        self.region = os.getenv('AWS_REGION', 'ap-southeast-1')
        self.account_id = os.getenv('AWS_ACCOUNT_ID')
        self.customer_name = os.getenv('CUSTOMER_NAME', 'AWS Customer')
        
        # Validate credentials
        if not self.access_key or not self.secret_key:
            raise ValueError("AWS credentials tidak ditemukan di .env file")
        
        # Initialize boto3 session
        self.session = boto3.Session(
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region
        )
        
        # Data storage
        self.assessment_data = {
            'customer_name': self.customer_name,
            'account_id': self.account_id,
            'region': self.region,
            'assessment_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'billing_data': {},
            'services': {},
            'security_findings': []
        }
        
        print(f"✓ AWS Assessment initialized untuk customer: {self.customer_name}")
        print(f"✓ Region: {self.region}")
    
    def validate_credentials(self):
        """Validasi AWS credentials dan permissions"""
        try:
            sts = self.session.client('sts')
            identity = sts.get_caller_identity()
            
            self.account_id = identity['Account']
            self.assessment_data['account_id'] = self.account_id
            
            print(f"✓ Credentials valid")
            print(f"✓ Account ID: {self.account_id}")
            print(f"✓ User ARN: {identity['Arn']}")
            return True
        except Exception as e:
            print(f"✗ Error validating credentials: {str(e)}")
            return False
    
    def get_billing_data(self):
        """Ambil data billing satu bulan terakhir dari Cost Explorer"""
        print(f"\n📊 Mengambil data billing bulan lalu...")
        
        try:
            ce = self.session.client('ce', region_name='us-east-1')  # Cost Explorer hanya di us-east-1
            
            # Calculate date range - bulan lalu saja
            end_date = datetime.now().date().replace(day=1)  # Awal bulan ini
            start_date = (end_date - timedelta(days=1)).replace(day=1)  # Awal bulan lalu
            
            print(f"  Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
            
            # Get total cost first (without grouping) - try multiple metrics
            response_total = ce.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date.strftime('%Y-%m-%d'),
                    'End': end_date.strftime('%Y-%m-%d')
                },
                Granularity='MONTHLY',
                Metrics=['UnblendedCost', 'BlendedCost']
            )
            
            # Get cost by service
            response = ce.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date.strftime('%Y-%m-%d'),
                    'End': end_date.strftime('%Y-%m-%d')
                },
                Granularity='MONTHLY',
                Metrics=['UnblendedCost'],
                GroupBy=[
                    {'Type': 'DIMENSION', 'Key': 'SERVICE'}
                ]
            )
            
            # Process billing data
            monthly_costs = []
            service_costs = {}
            
            # Get total from ungrouped response - try UnblendedCost first
            total_cost_actual = 0
            total_cost_blended = 0
            if response_total['ResultsByTime']:
                result = response_total['ResultsByTime'][0]
                total_cost_actual = float(result['Total']['UnblendedCost']['Amount'])
                total_cost_blended = float(result['Total']['BlendedCost']['Amount'])
            
            for result in response['ResultsByTime']:
                period = result['TimePeriod']['Start']
                total_cost = 0
                
                for group in result['Groups']:
                    service = group['Keys'][0]
                    cost = float(group['Metrics']['UnblendedCost']['Amount'])
                    
                    if cost > 0:
                        if service not in service_costs:
                            service_costs[service] = []
                        service_costs[service].append({
                            'period': period,
                            'cost': cost
                        })
                        total_cost += cost
                
                monthly_costs.append({
                    'period': period,
                    'total': total_cost_actual if total_cost_actual > 0 else total_cost  # Use actual total
                })
            
            self.assessment_data['billing_data'] = {
                'monthly_costs': monthly_costs,
                'service_costs': service_costs,
                'period': f"Bulan Lalu: {start_date.strftime('%B %Y')}",
                'total_actual': total_cost_actual,
                'total_blended': total_cost_blended
            }
            
            # Get top services
            total_by_service = {}
            for service, costs in service_costs.items():
                total_by_service[service] = sum(c['cost'] for c in costs)
            
            top_services = sorted(total_by_service.items(), key=lambda x: x[1], reverse=True)[:10]
            self.assessment_data['billing_data']['top_services'] = top_services
            
            print(f"✓ Data billing berhasil diambil")
            print(f"✓ Period: {start_date.strftime('%B %Y')}")
            print(f"✓ Total Actual Cost: ${total_cost_actual:.2f}")
            print(f"✓ Total services dengan biaya: {len(service_costs)}")
            print(f"✓ Top 3 services:")
            for service, cost in top_services[:3]:
                print(f"  - {service}: ${cost:.2f}")
            
            return True
            
        except Exception as e:
            print(f"✗ Error getting billing data: {str(e)}")
            print(f"  Note: Pastikan Cost Explorer API sudah diaktifkan di account AWS")
            return False
    
    def inventory_ec2(self):
        """Inventory EC2 instances"""
        print("\n🖥️  Inventarisasi EC2 instances...")
        try:
            ec2 = self.session.client('ec2')
            
            instances = ec2.describe_instances()
            instance_list = []
            
            for reservation in instances['Reservations']:
                for instance in reservation['Instances']:
                    instance_list.append({
                        'id': instance['InstanceId'],
                        'type': instance['InstanceType'],
                        'state': instance['State']['Name'],
                        'launch_time': instance['LaunchTime'].strftime('%Y-%m-%d %H:%M:%S')
                    })
            
            self.assessment_data['services']['ec2'] = {
                'count': len(instance_list),
                'instances': instance_list
            }
            
            print(f"✓ Found {len(instance_list)} EC2 instances")
            return True
        except Exception as e:
            print(f"✗ Error inventorying EC2: {str(e)}")
            return False
    
    def inventory_s3(self):
        """Inventory S3 buckets"""
        print("\n🪣 Inventarisasi S3 buckets...")
        try:
            s3 = self.session.client('s3')
            
            buckets = s3.list_buckets()
            bucket_list = []
            
            for bucket in buckets['Buckets']:
                bucket_list.append({
                    'name': bucket['Name'],
                    'creation_date': bucket['CreationDate'].strftime('%Y-%m-%d %H:%M:%S')
                })
            
            self.assessment_data['services']['s3'] = {
                'count': len(bucket_list),
                'buckets': bucket_list
            }
            
            print(f"✓ Found {len(bucket_list)} S3 buckets")
            return True
        except Exception as e:
            print(f"✗ Error inventorying S3: {str(e)}")
            return False
    
    def inventory_rds(self):
        """Inventory RDS instances"""
        print("\n🗄️  Inventarisasi RDS instances...")
        try:
            rds = self.session.client('rds')
            
            instances = rds.describe_db_instances()
            instance_list = []
            
            for instance in instances['DBInstances']:
                instance_list.append({
                    'id': instance['DBInstanceIdentifier'],
                    'engine': instance['Engine'],
                    'class': instance['DBInstanceClass'],
                    'status': instance['DBInstanceStatus']
                })
            
            self.assessment_data['services']['rds'] = {
                'count': len(instance_list),
                'instances': instance_list
            }
            
            print(f"✓ Found {len(instance_list)} RDS instances")
            return True
        except Exception as e:
            print(f"✗ Error inventorying RDS: {str(e)}")
            return False
    
    def inventory_lambda(self):
        """Inventory Lambda functions"""
        print("\n⚡ Inventarisasi Lambda functions...")
        try:
            lambda_client = self.session.client('lambda')
            
            functions = lambda_client.list_functions()
            function_list = []
            
            for func in functions['Functions']:
                function_list.append({
                    'name': func['FunctionName'],
                    'runtime': func['Runtime'],
                    'memory': func['MemorySize'],
                    'last_modified': func['LastModified']
                })
            
            self.assessment_data['services']['lambda'] = {
                'count': len(function_list),
                'functions': function_list
            }
            
            print(f"✓ Found {len(function_list)} Lambda functions")
            return True
        except Exception as e:
            print(f"✗ Error inventorying Lambda: {str(e)}")
            return False
    
    def inventory_dynamodb(self):
        """Inventory DynamoDB tables"""
        print("\n🗃️  Inventarisasi DynamoDB tables...")
        try:
            dynamodb = self.session.client('dynamodb')
            
            tables = dynamodb.list_tables()
            table_list = []
            
            for table_name in tables.get('TableNames', []):
                try:
                    table_info = dynamodb.describe_table(TableName=table_name)
                    table = table_info['Table']
                    table_list.append({
                        'name': table['TableName'],
                        'status': table['TableStatus'],
                        'item_count': table.get('ItemCount', 0),
                        'size_bytes': table.get('TableSizeBytes', 0)
                    })
                except Exception as e:
                    print(f"  ⚠ Error describing table {table_name}: {str(e)}")
            
            self.assessment_data['services']['dynamodb'] = {
                'count': len(table_list),
                'tables': table_list
            }
            
            print(f"✓ Found {len(table_list)} DynamoDB tables")
            return True
        except Exception as e:
            print(f"✗ Error inventorying DynamoDB: {str(e)}")
            return False
    
    def inventory_cloudfront(self):
        """Inventory CloudFront distributions"""
        print("\n🌐 Inventarisasi CloudFront distributions...")
        try:
            cloudfront = self.session.client('cloudfront')
            
            distributions = cloudfront.list_distributions()
            dist_list = []
            
            if 'DistributionList' in distributions and 'Items' in distributions['DistributionList']:
                for dist in distributions['DistributionList']['Items']:
                    dist_list.append({
                        'id': dist['Id'],
                        'domain': dist['DomainName'],
                        'status': dist['Status'],
                        'enabled': dist['Enabled']
                    })
            
            self.assessment_data['services']['cloudfront'] = {
                'count': len(dist_list),
                'distributions': dist_list
            }
            
            print(f"✓ Found {len(dist_list)} CloudFront distributions")
            return True
        except Exception as e:
            print(f"✗ Error inventorying CloudFront: {str(e)}")
            return False
    
    def inventory_elb(self):
        """Inventory Elastic Load Balancers"""
        print("\n⚖️  Inventarisasi Load Balancers...")
        try:
            elbv2 = self.session.client('elbv2')
            
            load_balancers = elbv2.describe_load_balancers()
            lb_list = []
            
            for lb in load_balancers.get('LoadBalancers', []):
                lb_list.append({
                    'name': lb['LoadBalancerName'],
                    'type': lb['Type'],
                    'scheme': lb['Scheme'],
                    'state': lb['State']['Code'],
                    'dns': lb['DNSName']
                })
            
            self.assessment_data['services']['elb'] = {
                'count': len(lb_list),
                'load_balancers': lb_list
            }
            
            print(f"✓ Found {len(lb_list)} Load Balancers")
            return True
        except Exception as e:
            print(f"✗ Error inventorying ELB: {str(e)}")
            return False
    
    def inventory_eks(self):
        """Inventory EKS clusters"""
        print("\n☸️  Inventarisasi EKS clusters...")
        try:
            eks = self.session.client('eks')
            
            clusters = eks.list_clusters()
            cluster_list = []
            
            for cluster_name in clusters.get('clusters', []):
                try:
                    cluster_info = eks.describe_cluster(name=cluster_name)
                    cluster = cluster_info['cluster']
                    cluster_list.append({
                        'name': cluster['name'],
                        'status': cluster['status'],
                        'version': cluster['version'],
                        'endpoint': cluster.get('endpoint', 'N/A'),
                        'created_at': cluster['createdAt'].strftime('%Y-%m-%d %H:%M:%S')
                    })
                except Exception as e:
                    print(f"  ⚠ Error describing cluster {cluster_name}: {str(e)}")
            
            self.assessment_data['services']['eks'] = {
                'count': len(cluster_list),
                'clusters': cluster_list
            }
            
            print(f"✓ Found {len(cluster_list)} EKS clusters")
            return True
        except Exception as e:
            print(f"✗ Error inventorying EKS: {str(e)}")
            return False
    
    def inventory_ebs(self):
        """Inventory EBS volumes"""
        print("\n💾 Inventarisasi EBS volumes...")
        try:
            ec2 = self.session.client('ec2')
            
            volumes = ec2.describe_volumes()
            volume_list = []
            
            for volume in volumes.get('Volumes', []):
                volume_list.append({
                    'id': volume['VolumeId'],
                    'size': volume['Size'],
                    'type': volume['VolumeType'],
                    'state': volume['State'],
                    'iops': volume.get('Iops', 'N/A'),
                    'encrypted': volume.get('Encrypted', False)
                })
            
            self.assessment_data['services']['ebs'] = {
                'count': len(volume_list),
                'volumes': volume_list
            }
            
            print(f"✓ Found {len(volume_list)} EBS volumes")
            return True
        except Exception as e:
            print(f"✗ Error inventorying EBS: {str(e)}")
            return False
    
    def inventory_elasticache(self):
        """Inventory ElastiCache clusters"""
        print("\n🔴 Inventarisasi ElastiCache clusters...")
        try:
            elasticache = self.session.client('elasticache')
            
            clusters = elasticache.describe_cache_clusters()
            cluster_list = []
            
            for cluster in clusters.get('CacheClusters', []):
                cluster_list.append({
                    'id': cluster['CacheClusterId'],
                    'engine': cluster['Engine'],
                    'engine_version': cluster['EngineVersion'],
                    'node_type': cluster['CacheNodeType'],
                    'status': cluster['CacheClusterStatus'],
                    'num_nodes': cluster['NumCacheNodes']
                })
            
            self.assessment_data['services']['elasticache'] = {
                'count': len(cluster_list),
                'clusters': cluster_list
            }
            
            print(f"✓ Found {len(cluster_list)} ElastiCache clusters")
            return True
        except Exception as e:
            print(f"✗ Error inventorying ElastiCache: {str(e)}")
            return False
    
    def inventory_vpc(self):
        """Inventory VPCs"""
        print("\n🌐 Inventarisasi VPCs...")
        try:
            ec2 = self.session.client('ec2')
            
            vpcs = ec2.describe_vpcs()
            vpc_list = []
            
            for vpc in vpcs.get('Vpcs', []):
                # Get VPC name from tags
                vpc_name = 'N/A'
                if 'Tags' in vpc:
                    for tag in vpc['Tags']:
                        if tag['Key'] == 'Name':
                            vpc_name = tag['Value']
                            break
                
                vpc_list.append({
                    'id': vpc['VpcId'],
                    'name': vpc_name,
                    'cidr': vpc['CidrBlock'],
                    'is_default': vpc.get('IsDefault', False),
                    'state': vpc['State']
                })
            
            self.assessment_data['services']['vpc'] = {
                'count': len(vpc_list),
                'vpcs': vpc_list
            }
            
            print(f"✓ Found {len(vpc_list)} VPCs")
            return True
        except Exception as e:
            print(f"✗ Error inventorying VPC: {str(e)}")
            return False
    
    def inventory_nat_gateway(self):
        """Inventory NAT Gateways"""
        print("\n🚪 Inventarisasi NAT Gateways...")
        try:
            ec2 = self.session.client('ec2')
            
            nat_gateways = ec2.describe_nat_gateways()
            nat_list = []
            
            for nat in nat_gateways.get('NatGateways', []):
                nat_list.append({
                    'id': nat['NatGatewayId'],
                    'vpc_id': nat['VpcId'],
                    'subnet_id': nat['SubnetId'],
                    'state': nat['State'],
                    'connectivity_type': nat.get('ConnectivityType', 'public')
                })
            
            self.assessment_data['services']['nat_gateway'] = {
                'count': len(nat_list),
                'nat_gateways': nat_list
            }
            
            print(f"✓ Found {len(nat_list)} NAT Gateways")
            return True
        except Exception as e:
            print(f"✗ Error inventorying NAT Gateway: {str(e)}")
            return False
    
    def inventory_kms(self):
        """Inventory KMS keys"""
        print("\n🔐 Inventarisasi KMS keys...")
        try:
            kms = self.session.client('kms')
            
            keys = kms.list_keys()
            key_list = []
            
            for key in keys.get('Keys', []):
                try:
                    key_metadata = kms.describe_key(KeyId=key['KeyId'])
                    metadata = key_metadata['KeyMetadata']
                    
                    # Skip AWS managed keys
                    if metadata['KeyManager'] == 'AWS':
                        continue
                    
                    key_list.append({
                        'id': metadata['KeyId'],
                        'arn': metadata['Arn'],
                        'state': metadata['KeyState'],
                        'enabled': metadata['Enabled'],
                        'created_date': metadata['CreationDate'].strftime('%Y-%m-%d %H:%M:%S')
                    })
                except Exception as e:
                    print(f"  ⚠ Error describing key {key['KeyId']}: {str(e)}")
            
            self.assessment_data['services']['kms'] = {
                'count': len(key_list),
                'keys': key_list
            }
            
            print(f"✓ Found {len(key_list)} customer-managed KMS keys")
            return True
        except Exception as e:
            print(f"✗ Error inventorying KMS: {str(e)}")
            return False
    
    def inventory_waf(self):
        """Inventory WAF Web ACLs"""
        print("\n🛡️  Inventarisasi WAF Web ACLs...")
        try:
            wafv2 = self.session.client('wafv2')
            
            # Get regional Web ACLs
            regional_acls = wafv2.list_web_acls(Scope='REGIONAL')
            acl_list = []
            
            for acl in regional_acls.get('WebACLs', []):
                acl_list.append({
                    'name': acl['Name'],
                    'id': acl['Id'],
                    'arn': acl['ARN'],
                    'scope': 'REGIONAL'
                })
            
            # Get CloudFront Web ACLs (global)
            try:
                wafv2_global = self.session.client('wafv2', region_name='us-east-1')
                cloudfront_acls = wafv2_global.list_web_acls(Scope='CLOUDFRONT')
                
                for acl in cloudfront_acls.get('WebACLs', []):
                    acl_list.append({
                        'name': acl['Name'],
                        'id': acl['Id'],
                        'arn': acl['ARN'],
                        'scope': 'CLOUDFRONT'
                    })
            except Exception as e:
                print(f"  ⚠ Could not check CloudFront WAF ACLs: {str(e)}")
            
            self.assessment_data['services']['waf'] = {
                'count': len(acl_list),
                'web_acls': acl_list
            }
            
            print(f"✓ Found {len(acl_list)} WAF Web ACLs")
            return True
        except Exception as e:
            print(f"✗ Error inventorying WAF: {str(e)}")
            return False
    
    def inventory_cloudwatch(self):
        """Inventory CloudWatch alarms"""
        print("\n📊 Inventarisasi CloudWatch alarms...")
        try:
            cloudwatch = self.session.client('cloudwatch')
            
            alarms = cloudwatch.describe_alarms()
            alarm_list = []
            
            for alarm in alarms.get('MetricAlarms', []):
                alarm_list.append({
                    'name': alarm['AlarmName'],
                    'state': alarm['StateValue'],
                    'metric': alarm['MetricName'],
                    'namespace': alarm['Namespace'],
                    'actions_enabled': alarm['ActionsEnabled']
                })
            
            self.assessment_data['services']['cloudwatch'] = {
                'count': len(alarm_list),
                'alarms': alarm_list
            }
            
            print(f"✓ Found {len(alarm_list)} CloudWatch alarms")
            return True
        except Exception as e:
            print(f"✗ Error inventorying CloudWatch: {str(e)}")
            return False
    
    def inventory_cloudtrail(self):
        """Inventory CloudTrail trails"""
        print("\n🔍 Inventarisasi CloudTrail trails...")
        try:
            cloudtrail = self.session.client('cloudtrail')
            
            trails = cloudtrail.describe_trails()
            trail_list = []
            
            for trail in trails.get('trailList', []):
                # Get trail status
                try:
                    status = cloudtrail.get_trail_status(Name=trail['TrailARN'])
                    is_logging = status.get('IsLogging', False)
                except:
                    is_logging = False
                
                trail_list.append({
                    'name': trail['Name'],
                    'arn': trail['TrailARN'],
                    'is_logging': is_logging,
                    'is_multi_region': trail.get('IsMultiRegionTrail', False),
                    's3_bucket': trail.get('S3BucketName', 'N/A')
                })
            
            self.assessment_data['services']['cloudtrail'] = {
                'count': len(trail_list),
                'trails': trail_list
            }
            
            print(f"✓ Found {len(trail_list)} CloudTrail trails")
            return True
        except Exception as e:
            print(f"✗ Error inventorying CloudTrail: {str(e)}")
            return False
    
    def inventory_config(self):
        """Inventory AWS Config recorders"""
        print("\n⚙️  Inventarisasi AWS Config recorders...")
        try:
            config = self.session.client('config')
            
            recorders = config.describe_configuration_recorders()
            recorder_list = []
            
            for recorder in recorders.get('ConfigurationRecorders', []):
                # Get recorder status
                try:
                    status_response = config.describe_configuration_recorder_status(
                        ConfigurationRecorderNames=[recorder['name']]
                    )
                    status = status_response['ConfigurationRecordersStatus'][0]
                    is_recording = status.get('recording', False)
                except:
                    is_recording = False
                
                recorder_list.append({
                    'name': recorder['name'],
                    'role_arn': recorder.get('roleARN', 'N/A'),
                    'is_recording': is_recording,
                    'record_all': recorder.get('recordingGroup', {}).get('allSupported', False)
                })
            
            self.assessment_data['services']['config'] = {
                'count': len(recorder_list),
                'recorders': recorder_list
            }
            
            print(f"✓ Found {len(recorder_list)} AWS Config recorders")
            return True
        except Exception as e:
            print(f"✗ Error inventorying AWS Config: {str(e)}")
            return False
    
    def inventory_efs(self):
        """Inventory EFS file systems"""
        print("\n📁 Inventarisasi EFS file systems...")
        try:
            efs = self.session.client('efs')
            
            file_systems = efs.describe_file_systems()
            fs_list = []
            
            for fs in file_systems.get('FileSystems', []):
                fs_list.append({
                    'id': fs['FileSystemId'],
                    'name': fs.get('Name', 'N/A'),
                    'creation_time': fs['CreationTime'].strftime('%Y-%m-%d %H:%M:%S'),
                    'life_cycle_state': fs['LifeCycleState'],
                    'number_of_mount_targets': fs['NumberOfMountTargets'],
                    'size_in_bytes': fs['SizeInBytes']['Value'],
                    'encrypted': fs.get('Encrypted', False)
                })
            
            self.assessment_data['services']['efs'] = {
                'count': len(fs_list),
                'file_systems': fs_list
            }
            
            print(f"✓ Found {len(fs_list)} EFS file systems")
            return True
        except Exception as e:
            print(f"✗ Error inventorying EFS: {str(e)}")
            return False
    
    def inventory_backup(self):
        """Inventory AWS Backup vaults and plans"""
        print("\n💾 Inventarisasi AWS Backup...")
        try:
            backup = self.session.client('backup')
            
            # Get backup vaults
            vaults = backup.list_backup_vaults()
            vault_list = []
            
            for vault in vaults.get('BackupVaultList', []):
                vault_list.append({
                    'name': vault['BackupVaultName'],
                    'arn': vault['BackupVaultArn'],
                    'creation_date': vault.get('CreationDate', 'N/A').strftime('%Y-%m-%d %H:%M:%S') if vault.get('CreationDate') else 'N/A',
                    'number_of_recovery_points': vault.get('NumberOfRecoveryPoints', 0)
                })
            
            # Get backup plans
            plans = backup.list_backup_plans()
            plan_list = []
            
            for plan in plans.get('BackupPlansList', []):
                plan_list.append({
                    'id': plan['BackupPlanId'],
                    'name': plan['BackupPlanName'],
                    'version_id': plan['VersionId'],
                    'creation_date': plan.get('CreationDate', 'N/A').strftime('%Y-%m-%d %H:%M:%S') if plan.get('CreationDate') else 'N/A'
                })
            
            self.assessment_data['services']['backup'] = {
                'count': len(vault_list) + len(plan_list),
                'vaults': vault_list,
                'plans': plan_list
            }
            
            print(f"✓ Found {len(vault_list)} backup vaults and {len(plan_list)} backup plans")
            return True
        except Exception as e:
            print(f"✗ Error inventorying AWS Backup: {str(e)}")
            return False
    
    def inventory_alb(self):
        """Inventory Application Load Balancers (ALB)"""
        print("\n⚖️  Inventarisasi Application Load Balancers...")
        try:
            elbv2 = self.session.client('elbv2')
            
            load_balancers = elbv2.describe_load_balancers()
            alb_list = []
            
            for lb in load_balancers.get('LoadBalancers', []):
                # Filter hanya ALB (Application Load Balancer)
                if lb['Type'] == 'application':
                    alb_list.append({
                        'name': lb['LoadBalancerName'],
                        'arn': lb['LoadBalancerArn'],
                        'dns': lb['DNSName'],
                        'scheme': lb['Scheme'],
                        'state': lb['State']['Code'],
                        'vpc_id': lb['VpcId'],
                        'availability_zones': [az['ZoneName'] for az in lb['AvailabilityZones']]
                    })
            
            self.assessment_data['services']['alb'] = {
                'count': len(alb_list),
                'load_balancers': alb_list
            }
            
            print(f"✓ Found {len(alb_list)} Application Load Balancers")
            return True
        except Exception as e:
            print(f"✗ Error inventorying ALB: {str(e)}")
            return False
    
    def inventory_secretsmanager(self):
        """Inventory Secrets Manager secrets"""
        print("\n🔑 Inventarisasi Secrets Manager...")
        try:
            secretsmanager = self.session.client('secretsmanager')
            
            secrets = secretsmanager.list_secrets()
            secret_list = []
            
            for secret in secrets.get('SecretList', []):
                secret_list.append({
                    'name': secret['Name'],
                    'arn': secret['ARN'],
                    'description': secret.get('Description', 'N/A'),
                    'last_changed_date': secret.get('LastChangedDate', 'N/A').strftime('%Y-%m-%d %H:%M:%S') if secret.get('LastChangedDate') else 'N/A',
                    'last_accessed_date': secret.get('LastAccessedDate', 'N/A').strftime('%Y-%m-%d') if secret.get('LastAccessedDate') else 'N/A',
                    'rotation_enabled': secret.get('RotationEnabled', False)
                })
            
            self.assessment_data['services']['secretsmanager'] = {
                'count': len(secret_list),
                'secrets': secret_list
            }
            
            print(f"✓ Found {len(secret_list)} secrets")
            return True
        except Exception as e:
            print(f"✗ Error inventorying Secrets Manager: {str(e)}")
            return False
    
    def inventory_sns(self):
        """Inventory SNS topics"""
        print("\n📢 Inventarisasi SNS topics...")
        try:
            sns = self.session.client('sns')
            
            topics = sns.list_topics()
            topic_list = []
            
            for topic in topics.get('Topics', []):
                topic_arn = topic['TopicArn']
                
                # Get topic attributes
                try:
                    attrs = sns.get_topic_attributes(TopicArn=topic_arn)
                    attributes = attrs['Attributes']
                    
                    topic_list.append({
                        'arn': topic_arn,
                        'name': topic_arn.split(':')[-1],
                        'display_name': attributes.get('DisplayName', 'N/A'),
                        'subscriptions_confirmed': attributes.get('SubscriptionsConfirmed', '0'),
                        'subscriptions_pending': attributes.get('SubscriptionsPending', '0')
                    })
                except Exception as e:
                    print(f"  ⚠ Error getting attributes for topic {topic_arn}: {str(e)}")
            
            self.assessment_data['services']['sns'] = {
                'count': len(topic_list),
                'topics': topic_list
            }
            
            print(f"✓ Found {len(topic_list)} SNS topics")
            return True
        except Exception as e:
            print(f"✗ Error inventorying SNS: {str(e)}")
            return False
    
    def inventory_msk(self):
        """Inventory MSK (Managed Streaming for Apache Kafka) clusters"""
        print("\n📊 Inventarisasi MSK clusters...")
        try:
            kafka = self.session.client('kafka')
            
            clusters = kafka.list_clusters_v2()
            cluster_list = []
            
            for cluster in clusters.get('ClusterInfoList', []):
                cluster_list.append({
                    'name': cluster['ClusterName'],
                    'arn': cluster['ClusterArn'],
                    'cluster_type': cluster['ClusterType'],
                    'state': cluster['State'],
                    'creation_time': cluster.get('CreationTime', 'N/A').strftime('%Y-%m-%d %H:%M:%S') if cluster.get('CreationTime') else 'N/A'
                })
            
            self.assessment_data['services']['msk'] = {
                'count': len(cluster_list),
                'clusters': cluster_list
            }
            
            print(f"✓ Found {len(cluster_list)} MSK clusters")
            return True
        except Exception as e:
            print(f"✗ Error inventorying MSK: {str(e)}")
            return False
    
    def inventory_amazonmq(self):
        """Inventory Amazon MQ brokers"""
        print("\n🔄 Inventarisasi Amazon MQ brokers...")
        try:
            mq = self.session.client('mq')
            
            brokers = mq.list_brokers()
            broker_list = []
            
            for broker in brokers.get('BrokerSummaries', []):
                broker_list.append({
                    'id': broker['BrokerId'],
                    'name': broker['BrokerName'],
                    'broker_state': broker['BrokerState'],
                    'deployment_mode': broker['DeploymentMode'],
                    'engine_type': broker['EngineType'],
                    'host_instance_type': broker.get('HostInstanceType', 'N/A'),
                    'created': broker.get('Created', 'N/A').strftime('%Y-%m-%d %H:%M:%S') if broker.get('Created') else 'N/A'
                })
            
            self.assessment_data['services']['amazonmq'] = {
                'count': len(broker_list),
                'brokers': broker_list
            }
            
            print(f"✓ Found {len(broker_list)} Amazon MQ brokers")
            return True
        except Exception as e:
            print(f"✗ Error inventorying Amazon MQ: {str(e)}")
            return False
    
    def inventory_glue(self):
        """Inventory AWS Glue databases and jobs"""
        print("\n🔧 Inventarisasi AWS Glue...")
        try:
            glue = self.session.client('glue')
            
            # Get Glue databases
            databases = glue.get_databases()
            db_list = []
            
            for db in databases.get('DatabaseList', []):
                db_list.append({
                    'name': db['Name'],
                    'description': db.get('Description', 'N/A'),
                    'create_time': db.get('CreateTime', 'N/A').strftime('%Y-%m-%d %H:%M:%S') if db.get('CreateTime') else 'N/A'
                })
            
            # Get Glue jobs
            jobs = glue.get_jobs()
            job_list = []
            
            for job in jobs.get('Jobs', []):
                job_list.append({
                    'name': job['Name'],
                    'role': job.get('Role', 'N/A'),
                    'created_on': job.get('CreatedOn', 'N/A').strftime('%Y-%m-%d %H:%M:%S') if job.get('CreatedOn') else 'N/A',
                    'glue_version': job.get('GlueVersion', 'N/A'),
                    'max_capacity': job.get('MaxCapacity', 'N/A')
                })
            
            self.assessment_data['services']['glue'] = {
                'count': len(db_list) + len(job_list),
                'databases': db_list,
                'jobs': job_list
            }
            
            print(f"✓ Found {len(db_list)} Glue databases and {len(job_list)} Glue jobs")
            return True
        except Exception as e:
            print(f"✗ Error inventorying AWS Glue: {str(e)}")
            return False
    
    def load_services_config(self):
        """Load services configuration dari services.md"""
        import re
        
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
            if os.path.exists('services.md'):
                with open('services.md', 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Stop parsing at "Contoh Penggunaan" or "---" section
                # Split content and only parse the main table section
                if '## Contoh Penggunaan' in content:
                    content = content.split('## Contoh Penggunaan')[0]
                elif '---\n\n##' in content:
                    # Find last --- before examples
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
                print(f"✓ Loaded services config dari services.md: {enabled_count} services enabled")
                
                # Debug: Print lambda status
                if 'lambda' in services:
                    print(f"  DEBUG: Lambda enabled = {services['lambda']['enabled']}")
                
                return services
            else:
                print("⚠ services.md tidak ditemukan, menggunakan default services")
                return {
                    'ec2': {'enabled': True},
                    's3': {'enabled': True},
                    'rds': {'enabled': True},
                    'lambda': {'enabled': True}
                }
        except Exception as e:
            print(f"✗ Error loading services config: {str(e)}")
            return {}
    
    def run_assessment(self):
        """Jalankan full assessment"""
        print("\n" + "="*60)
        print("🚀 Memulai AWS Account Assessment")
        print("="*60)
        
        # Step 1: Validate credentials
        if not self.validate_credentials():
            print("\n✗ Assessment gagal: Credentials tidak valid")
            return False
        
        # Step 2: Get billing data (PRIORITAS)
        self.get_billing_data()
        
        # Step 3: Load services configuration
        services_config = self.load_services_config()
        
        # Step 4: Inventory services (dinamis berdasarkan config)
        print("\n" + "="*60)
        print("📦 Inventarisasi Services")
        print("="*60)
        
        # Mapping service name ke inventory function
        inventory_functions = {
            'ec2': self.inventory_ec2,
            's3': self.inventory_s3,
            'rds': self.inventory_rds,
            'lambda': self.inventory_lambda,
            'dynamodb': self.inventory_dynamodb,
            'cloudfront': self.inventory_cloudfront,
            'elb': self.inventory_elb,
            'eks': self.inventory_eks,
            'ebs': self.inventory_ebs,
            'elasticache': self.inventory_elasticache,
            'vpc': self.inventory_vpc,
            'nat_gateway': self.inventory_nat_gateway,
            'kms': self.inventory_kms,
            'waf': self.inventory_waf,
            'cloudwatch': self.inventory_cloudwatch,
            'cloudtrail': self.inventory_cloudtrail,
            'config': self.inventory_config,
            'efs': self.inventory_efs,
            'backup': self.inventory_backup,
            'alb': self.inventory_alb,
            'secretsmanager': self.inventory_secretsmanager,
            'sns': self.inventory_sns,
            'msk': self.inventory_msk,
            'amazonmq': self.inventory_amazonmq,
            'glue': self.inventory_glue,
        }
        
        # Jalankan inventory hanya untuk services yang enabled
        for service_name, service_config in services_config.items():
            if service_config.get('enabled', False) and service_name in inventory_functions:
                print(f"\n→ Inventorying {service_name.upper()}...")
                try:
                    inventory_functions[service_name]()
                except Exception as e:
                    print(f"  ✗ Error: {str(e)}")
            elif service_name == 'lambda':
                # Debug lambda specifically
                print(f"\n  DEBUG: Lambda skipped - enabled={service_config.get('enabled', False)}")
        
        # Step 5: Save data
        self.save_assessment_data()
        
        print("\n" + "="*60)
        print("✓ Assessment selesai!")
        print("="*60)
        
        return True
    
    def _generate_services_inventory(self):
        """Generate HTML untuk services inventory secara dinamis"""
        services_html = ''
        
        # EC2 Section
        if 'ec2' in self.assessment_data['services']:
            ec2_data = self.assessment_data['services']['ec2']
            if ec2_data.get('count', 0) > 0:
                running_count = len([i for i in ec2_data['instances'] if i['state'] == 'running'])
                stopped_count = len([i for i in ec2_data['instances'] if i['state'] == 'stopped'])
                
                services_html += f'''
                <h3 id="ec2-section">EC2 - Compute Instances</h3>
                <div class="service-detail-card">
                    <div class="service-summary-stats">
                        <div class="stat-item">
                            <div class="stat-label">Total Instances</div>
                            <div class="stat-value">{ec2_data['count']}</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-label">Status</div>
                            <div class="stat-badges">
                                <span class="status-badge running">{running_count} Running</span>
                                <span class="status-badge stopped">{stopped_count} Stopped</span>
                            </div>
                        </div>
                    </div>
                    <div class="table-wrapper">
                        <table id="ec2-table">
                            <thead>
                                <tr>
                                    <th>Instance ID</th>
                                    <th>Type</th>
                                    <th>State</th>
                                    <th>Launch Time</th>
                                </tr>
                            </thead>
                            <tbody>
                '''
                
                # Add all instances
                for instance in ec2_data['instances']:
                    state_class = 'running' if instance['state'] == 'running' else 'stopped'
                    services_html += f'''
                    <tr>
                        <td>{instance['id']}</td>
                        <td>{instance['type']}</td>
                        <td><span class="status-badge {state_class}">{instance['state'].title()}</span></td>
                        <td>{instance['launch_time']}</td>
                    </tr>
                    '''
                
                services_html += '''
                            </tbody>
                        </table>
                    </div>
                    <div class="pagination" id="ec2-pagination"></div>
                </div>
                '''
        
        # S3 Section
        if 's3' in self.assessment_data['services']:
            s3_data = self.assessment_data['services']['s3']
            if s3_data.get('count', 0) > 0:
                services_html += f'''
                <h3>S3 - Simple Storage Service</h3>
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>Bucket Name</th>
                                <th>Creation Date</th>
                            </tr>
                        </thead>
                        <tbody>
                '''
                for bucket in s3_data['buckets']:
                    services_html += f'''
                    <tr>
                        <td>{bucket['name']}</td>
                        <td>{bucket['creation_date']}</td>
                    </tr>
                    '''
                services_html += '</tbody></table></div>'
        
        # RDS Section
        if 'rds' in self.assessment_data['services']:
            rds_data = self.assessment_data['services']['rds']
            if rds_data.get('count', 0) > 0:
                available_count = len([i for i in rds_data['instances'] if i['status'] == 'available'])
                other_count = rds_data['count'] - available_count
                
                services_html += f'''
                <h3 id="rds-section">RDS - Relational Database Service</h3>
                <div class="service-detail-card">
                    <div class="service-summary-stats">
                        <div class="stat-item">
                            <div class="stat-label">Total Instances</div>
                            <div class="stat-value">{rds_data['count']}</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-label">Status</div>
                            <div class="stat-badges">
                                <span class="status-badge available">{available_count} Available</span>
                                {f'<span class="status-badge inactive">{other_count} Other</span>' if other_count > 0 else ''}
                            </div>
                        </div>
                    </div>
                    <div class="table-wrapper">
                        <table id="rds-table">
                            <thead>
                                <tr>
                                    <th>Instance ID</th>
                                    <th>Engine</th>
                                    <th>Class</th>
                                    <th>Status</th>
                                </tr>
                            </thead>
                            <tbody>
                '''
                for instance in rds_data['instances']:
                    status_class = 'available' if instance['status'] == 'available' else 'inactive'
                    services_html += f'''
                    <tr>
                        <td>{instance['id']}</td>
                        <td>{instance['engine']}</td>
                        <td>{instance['class']}</td>
                        <td><span class="status-badge {status_class}">{instance['status'].title()}</span></td>
                    </tr>
                    '''
                services_html += '''
                            </tbody>
                        </table>
                    </div>
                    <div class="pagination" id="rds-pagination"></div>
                </div>
                '''
        
        # Lambda Section
        if 'lambda' in self.assessment_data['services']:
            lambda_data = self.assessment_data['services']['lambda']
            if lambda_data.get('count', 0) > 0:
                services_html += f'''
                <h3>Lambda - Serverless Functions</h3>
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>Function Name</th>
                                <th>Runtime</th>
                                <th>Memory (MB)</th>
                                <th>Last Modified</th>
                            </tr>
                        </thead>
                        <tbody>
                '''
                for func in lambda_data['functions']:
                    services_html += f'''
                    <tr>
                        <td>{func['name']}</td>
                        <td>{func['runtime']}</td>
                        <td>{func['memory']}</td>
                        <td>{func['last_modified']}</td>
                    </tr>
                    '''
                services_html += '</tbody></table></div>'
        
        # DynamoDB Section
        if 'dynamodb' in self.assessment_data['services']:
            dynamodb_data = self.assessment_data['services']['dynamodb']
            if dynamodb_data.get('count', 0) > 0:
                services_html += f'''
                <h3>DynamoDB - NoSQL Database</h3>
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>Table Name</th>
                                <th>Status</th>
                                <th>Item Count</th>
                                <th>Size (Bytes)</th>
                            </tr>
                        </thead>
                        <tbody>
                '''
                for table in dynamodb_data['tables']:
                    services_html += f'''
                    <tr>
                        <td>{table['name']}</td>
                        <td>{table['status']}</td>
                        <td>{table['item_count']:,}</td>
                        <td>{table['size_bytes']:,}</td>
                    </tr>
                    '''
                services_html += '</tbody></table></div>'
        
        # CloudFront Section
        if 'cloudfront' in self.assessment_data['services']:
            cf_data = self.assessment_data['services']['cloudfront']
            if cf_data.get('count', 0) > 0:
                services_html += f'''
                <h3>CloudFront - Content Delivery Network</h3>
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>Distribution ID</th>
                                <th>Domain Name</th>
                                <th>Status</th>
                                <th>Enabled</th>
                            </tr>
                        </thead>
                        <tbody>
                '''
                for dist in cf_data['distributions']:
                    services_html += f'''
                    <tr>
                        <td>{dist['id']}</td>
                        <td>{dist['domain']}</td>
                        <td>{dist['status']}</td>
                        <td>{'Yes' if dist['enabled'] else 'No'}</td>
                    </tr>
                    '''
                services_html += '</tbody></table></div>'
        
        # ELB Section
        if 'elb' in self.assessment_data['services']:
            elb_data = self.assessment_data['services']['elb']
            if elb_data.get('count', 0) > 0:
                services_html += f'''
                <h3>ELB - Elastic Load Balancing</h3>
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>Type</th>
                                <th>Scheme</th>
                                <th>State</th>
                            </tr>
                        </thead>
                        <tbody>
                '''
                for lb in elb_data['load_balancers']:
                    services_html += f'''
                    <tr>
                        <td>{lb['name']}</td>
                        <td>{lb['type']}</td>
                        <td>{lb['scheme']}</td>
                        <td>{lb['state']}</td>
                    </tr>
                    '''
                services_html += '</tbody></table></div>'
        
        # EKS Section
        if 'eks' in self.assessment_data['services']:
            eks_data = self.assessment_data['services']['eks']
            if eks_data.get('count', 0) > 0:
                services_html += f'''
                <h3>EKS - Elastic Kubernetes Service</h3>
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>Cluster Name</th>
                                <th>Status</th>
                                <th>Version</th>
                                <th>Created At</th>
                            </tr>
                        </thead>
                        <tbody>
                '''
                for cluster in eks_data['clusters']:
                    services_html += f'''
                    <tr>
                        <td>{cluster['name']}</td>
                        <td>{cluster['status']}</td>
                        <td>{cluster['version']}</td>
                        <td>{cluster['created_at']}</td>
                    </tr>
                    '''
                services_html += '</tbody></table></div>'
        
        # EBS Section
        if 'ebs' in self.assessment_data['services']:
            ebs_data = self.assessment_data['services']['ebs']
            if ebs_data.get('count', 0) > 0:
                services_html += f'''
                <h3>EBS - Elastic Block Store</h3>
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>Volume ID</th>
                                <th>Size (GB)</th>
                                <th>Type</th>
                                <th>State</th>
                                <th>Encrypted</th>
                            </tr>
                        </thead>
                        <tbody>
                '''
                for volume in ebs_data['volumes']:
                    services_html += f'''
                    <tr>
                        <td>{volume['id']}</td>
                        <td>{volume['size']}</td>
                        <td>{volume['type']}</td>
                        <td>{volume['state']}</td>
                        <td>{'Yes' if volume['encrypted'] else 'No'}</td>
                    </tr>
                    '''
                services_html += '</tbody></table></div>'
        
        # ElastiCache Section
        if 'elasticache' in self.assessment_data['services']:
            ec_data = self.assessment_data['services']['elasticache']
            if ec_data.get('count', 0) > 0:
                services_html += f'''
                <h3>ElastiCache - In-Memory Cache</h3>
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>Cluster ID</th>
                                <th>Engine</th>
                                <th>Node Type</th>
                                <th>Nodes</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                '''
                for cluster in ec_data['clusters']:
                    services_html += f'''
                    <tr>
                        <td>{cluster['id']}</td>
                        <td>{cluster['engine']} {cluster['engine_version']}</td>
                        <td>{cluster['node_type']}</td>
                        <td>{cluster['num_nodes']}</td>
                        <td>{cluster['status']}</td>
                    </tr>
                    '''
                services_html += '</tbody></table></div>'
        
        # VPC Section
        if 'vpc' in self.assessment_data['services']:
            vpc_data = self.assessment_data['services']['vpc']
            if vpc_data.get('count', 0) > 0:
                services_html += f'''
                <h3>VPC - Virtual Private Cloud</h3>
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>VPC ID</th>
                                <th>Name</th>
                                <th>CIDR Block</th>
                                <th>Default</th>
                                <th>State</th>
                            </tr>
                        </thead>
                        <tbody>
                '''
                for vpc in vpc_data['vpcs']:
                    services_html += f'''
                    <tr>
                        <td>{vpc['id']}</td>
                        <td>{vpc['name']}</td>
                        <td>{vpc['cidr']}</td>
                        <td>{'Yes' if vpc['is_default'] else 'No'}</td>
                        <td>{vpc['state']}</td>
                    </tr>
                    '''
                services_html += '</tbody></table></div>'
        
        # NAT Gateway Section
        if 'nat_gateway' in self.assessment_data['services']:
            nat_data = self.assessment_data['services']['nat_gateway']
            if nat_data.get('count', 0) > 0:
                services_html += f'''
                <h3>NAT Gateway</h3>
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>NAT Gateway ID</th>
                                <th>VPC ID</th>
                                <th>Subnet ID</th>
                                <th>State</th>
                            </tr>
                        </thead>
                        <tbody>
                '''
                for nat in nat_data['nat_gateways']:
                    services_html += f'''
                    <tr>
                        <td>{nat['id']}</td>
                        <td>{nat['vpc_id']}</td>
                        <td>{nat['subnet_id']}</td>
                        <td>{nat['state']}</td>
                    </tr>
                    '''
                services_html += '</tbody></table></div>'
        
        # KMS Section
        if 'kms' in self.assessment_data['services']:
            kms_data = self.assessment_data['services']['kms']
            if kms_data.get('count', 0) > 0:
                services_html += f'''
                <h3>KMS - Key Management Service</h3>
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>Key ID</th>
                                <th>State</th>
                                <th>Enabled</th>
                                <th>Created Date</th>
                            </tr>
                        </thead>
                        <tbody>
                '''
                for key in kms_data['keys']:
                    services_html += f'''
                    <tr>
                        <td>{key['id']}</td>
                        <td>{key['state']}</td>
                        <td>{'Yes' if key['enabled'] else 'No'}</td>
                        <td>{key['created_date']}</td>
                    </tr>
                    '''
                services_html += '</tbody></table></div>'
        
        # WAF Section
        if 'waf' in self.assessment_data['services']:
            waf_data = self.assessment_data['services']['waf']
            if waf_data.get('count', 0) > 0:
                services_html += f'''
                <h3>WAF - Web Application Firewall</h3>
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>Web ACL Name</th>
                                <th>Scope</th>
                                <th>ID</th>
                            </tr>
                        </thead>
                        <tbody>
                '''
                for acl in waf_data['web_acls']:
                    services_html += f'''
                    <tr>
                        <td>{acl['name']}</td>
                        <td>{acl['scope']}</td>
                        <td>{acl['id']}</td>
                    </tr>
                    '''
                services_html += '</tbody></table></div>'
        
        # CloudWatch Section
        if 'cloudwatch' in self.assessment_data['services']:
            cw_data = self.assessment_data['services']['cloudwatch']
            if cw_data.get('count', 0) > 0:
                services_html += f'''
                <h3>CloudWatch - Monitoring & Alarms</h3>
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>Alarm Name</th>
                                <th>State</th>
                                <th>Metric</th>
                                <th>Namespace</th>
                            </tr>
                        </thead>
                        <tbody>
                '''
                for alarm in cw_data['alarms']:
                    services_html += f'''
                    <tr>
                        <td>{alarm['name']}</td>
                        <td>{alarm['state']}</td>
                        <td>{alarm['metric']}</td>
                        <td>{alarm['namespace']}</td>
                    </tr>
                    '''
                services_html += '</tbody></table></div>'
        
        # CloudTrail Section
        if 'cloudtrail' in self.assessment_data['services']:
            ct_data = self.assessment_data['services']['cloudtrail']
            if ct_data.get('count', 0) > 0:
                services_html += f'''
                <h3>CloudTrail - Audit Logging</h3>
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>Trail Name</th>
                                <th>Logging</th>
                                <th>Multi-Region</th>
                                <th>S3 Bucket</th>
                            </tr>
                        </thead>
                        <tbody>
                '''
                for trail in ct_data['trails']:
                    services_html += f'''
                    <tr>
                        <td>{trail['name']}</td>
                        <td>{'Active' if trail['is_logging'] else 'Inactive'}</td>
                        <td>{'Yes' if trail['is_multi_region'] else 'No'}</td>
                        <td>{trail['s3_bucket']}</td>
                    </tr>
                    '''
                services_html += '</tbody></table></div>'
        
        # Config Section
        if 'config' in self.assessment_data['services']:
            config_data = self.assessment_data['services']['config']
            if config_data.get('count', 0) > 0:
                services_html += f'''
                <h3>AWS Config - Configuration Recorder</h3>
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>Recorder Name</th>
                                <th>Recording</th>
                                <th>Record All Resources</th>
                            </tr>
                        </thead>
                        <tbody>
                '''
                for recorder in config_data['recorders']:
                    services_html += f'''
                    <tr>
                        <td>{recorder['name']}</td>
                        <td>{'Active' if recorder['is_recording'] else 'Inactive'}</td>
                        <td>{'Yes' if recorder['record_all'] else 'No'}</td>
                    </tr>
                    '''
                services_html += '</tbody></table></div>'
        
        # EFS Section
        if 'efs' in self.assessment_data['services']:
            efs_data = self.assessment_data['services']['efs']
            if efs_data.get('count', 0) > 0:
                services_html += f'''
                <h3>EFS - Elastic File System</h3>
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>File System ID</th>
                                <th>Name</th>
                                <th>State</th>
                                <th>Mount Targets</th>
                                <th>Encrypted</th>
                            </tr>
                        </thead>
                        <tbody>
                '''
                for fs in efs_data['file_systems']:
                    services_html += f'''
                    <tr>
                        <td>{fs['id']}</td>
                        <td>{fs['name']}</td>
                        <td>{fs['life_cycle_state']}</td>
                        <td>{fs['number_of_mount_targets']}</td>
                        <td>{'Yes' if fs['encrypted'] else 'No'}</td>
                    </tr>
                    '''
                services_html += '</tbody></table></div>'
        
        # AWS Backup Section
        if 'backup' in self.assessment_data['services']:
            backup_data = self.assessment_data['services']['backup']
            if backup_data.get('count', 0) > 0:
                services_html += f'''
                <h3>AWS Backup</h3>
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>Type</th>
                                <th>Name</th>
                                <th>Details</th>
                            </tr>
                        </thead>
                        <tbody>
                '''
                for vault in backup_data.get('vaults', []):
                    services_html += f'''
                    <tr>
                        <td>Vault</td>
                        <td>{vault['name']}</td>
                        <td>Recovery Points: {vault['number_of_recovery_points']}</td>
                    </tr>
                    '''
                for plan in backup_data.get('plans', []):
                    services_html += f'''
                    <tr>
                        <td>Plan</td>
                        <td>{plan['name']}</td>
                        <td>ID: {plan['id']}</td>
                    </tr>
                    '''
                services_html += '</tbody></table></div>'
        
        # ALB Section
        if 'alb' in self.assessment_data['services']:
            alb_data = self.assessment_data['services']['alb']
            if alb_data.get('count', 0) > 0:
                services_html += f'''
                <h3>ALB - Application Load Balancer</h3>
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>DNS Name</th>
                                <th>Scheme</th>
                                <th>State</th>
                            </tr>
                        </thead>
                        <tbody>
                '''
                for lb in alb_data['load_balancers']:
                    services_html += f'''
                    <tr>
                        <td>{lb['name']}</td>
                        <td>{lb['dns']}</td>
                        <td>{lb['scheme']}</td>
                        <td>{lb['state']}</td>
                    </tr>
                    '''
                services_html += '</tbody></table></div>'
        
        # Secrets Manager Section
        if 'secretsmanager' in self.assessment_data['services']:
            sm_data = self.assessment_data['services']['secretsmanager']
            if sm_data.get('count', 0) > 0:
                services_html += f'''
                <h3>Secrets Manager</h3>
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>Secret Name</th>
                                <th>Description</th>
                                <th>Rotation Enabled</th>
                                <th>Last Changed</th>
                            </tr>
                        </thead>
                        <tbody>
                '''
                for secret in sm_data['secrets']:
                    services_html += f'''
                    <tr>
                        <td>{secret['name']}</td>
                        <td>{secret['description']}</td>
                        <td>{'Yes' if secret['rotation_enabled'] else 'No'}</td>
                        <td>{secret['last_changed_date']}</td>
                    </tr>
                    '''
                services_html += '</tbody></table></div>'
        
        # SNS Section
        if 'sns' in self.assessment_data['services']:
            sns_data = self.assessment_data['services']['sns']
            if sns_data.get('count', 0) > 0:
                services_html += f'''
                <h3>SNS - Simple Notification Service</h3>
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>Topic Name</th>
                                <th>Display Name</th>
                                <th>Subscriptions Confirmed</th>
                                <th>Subscriptions Pending</th>
                            </tr>
                        </thead>
                        <tbody>
                '''
                for topic in sns_data['topics']:
                    services_html += f'''
                    <tr>
                        <td>{topic['name']}</td>
                        <td>{topic['display_name']}</td>
                        <td>{topic['subscriptions_confirmed']}</td>
                        <td>{topic['subscriptions_pending']}</td>
                    </tr>
                    '''
                services_html += '</tbody></table></div>'
        
        # MSK Section
        if 'msk' in self.assessment_data['services']:
            msk_data = self.assessment_data['services']['msk']
            if msk_data.get('count', 0) > 0:
                services_html += f'''
                <h3>MSK - Managed Streaming for Apache Kafka</h3>
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>Cluster Name</th>
                                <th>Type</th>
                                <th>State</th>
                                <th>Created</th>
                            </tr>
                        </thead>
                        <tbody>
                '''
                for cluster in msk_data['clusters']:
                    services_html += f'''
                    <tr>
                        <td>{cluster['name']}</td>
                        <td>{cluster['cluster_type']}</td>
                        <td>{cluster['state']}</td>
                        <td>{cluster['creation_time']}</td>
                    </tr>
                    '''
                services_html += '</tbody></table></div>'
        
        # Amazon MQ Section
        if 'amazonmq' in self.assessment_data['services']:
            mq_data = self.assessment_data['services']['amazonmq']
            if mq_data.get('count', 0) > 0:
                services_html += f'''
                <h3>Amazon MQ</h3>
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>Broker Name</th>
                                <th>Engine Type</th>
                                <th>State</th>
                                <th>Deployment Mode</th>
                            </tr>
                        </thead>
                        <tbody>
                '''
                for broker in mq_data['brokers']:
                    services_html += f'''
                    <tr>
                        <td>{broker['name']}</td>
                        <td>{broker['engine_type']}</td>
                        <td>{broker['broker_state']}</td>
                        <td>{broker['deployment_mode']}</td>
                    </tr>
                    '''
                services_html += '</tbody></table></div>'
        
        # Glue Section
        if 'glue' in self.assessment_data['services']:
            glue_data = self.assessment_data['services']['glue']
            if glue_data.get('count', 0) > 0:
                services_html += f'''
                <h3>AWS Glue</h3>
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>Type</th>
                                <th>Name</th>
                                <th>Details</th>
                            </tr>
                        </thead>
                        <tbody>
                '''
                for db in glue_data.get('databases', []):
                    services_html += f'''
                    <tr>
                        <td>Database</td>
                        <td>{db['name']}</td>
                        <td>{db['description']}</td>
                    </tr>
                    '''
                for job in glue_data.get('jobs', []):
                    services_html += f'''
                    <tr>
                        <td>Job</td>
                        <td>{job['name']}</td>
                        <td>Glue Version: {job['glue_version']}</td>
                    </tr>
                    '''
                services_html += '</tbody></table></div>'
        
        if not services_html:
            services_html = '<p style="color: var(--text-muted); text-align: center; padding: 40px;">Tidak ada services yang ditemukan.</p>'
        
        return services_html
    
    
    def save_assessment_data(self):
        """Save assessment data ke JSON file"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"output/assessment_data_{timestamp}.json"
        
        os.makedirs('output', exist_ok=True)
        
        with open(filename, 'w') as f:
            json.dump(self.assessment_data, f, indent=2, cls=DecimalEncoder)
        
        print(f"\n✓ Assessment data saved to: {filename}")
        return filename
    
    def _generate_summary_services(self):
        """Generate HTML untuk Summary Services table"""
        summary_html = ''
        
        # Mapping service names untuk display yang lebih friendly
        service_display_names = {
            'ec2': 'EC2 (Compute)',
            'eks': 'EKS (Kubernetes)',
            's3': 'S3 (Storage)',
            'ebs': 'EBS (Volumes)',
            'rds': 'RDS (Database)',
            'elasticache': 'ElastiCache',
            'vpc': 'VPC',
            'elb': 'ELB (Load Balancer)',
            'alb': 'ALB (Application Load Balancer)',
            'nat_gateway': 'NAT Gateway',
            'waf': 'WAF',
            'cloudwatch': 'CloudWatch',
            'cloudtrail': 'CloudTrail',
            'kms': 'KMS',
            'secretsmanager': 'Secrets Manager',
            'efs': 'EFS',
            'backup': 'AWS Backup',
            'config': 'AWS Config',
            'lambda': 'Lambda',
            'dynamodb': 'DynamoDB',
            'cloudfront': 'CloudFront',
            'sns': 'SNS',
            'msk': 'MSK',
            'amazonmq': 'Amazon MQ',
            'glue': 'AWS Glue'
        }
        
        # Collect all services with their counts
        services_summary = []
        for service_key, service_data in self.assessment_data['services'].items():
            count = service_data.get('count', 0)
            if count > 0:
                display_name = service_display_names.get(service_key, service_key.upper())
                services_summary.append({
                    'name': display_name,
                    'count': count
                })
        
        # Sort by count descending
        services_summary.sort(key=lambda x: x['count'], reverse=True)
        
        # Generate HTML rows
        if services_summary:
            for service in services_summary:
                summary_html += f'''
                <tr>
                    <td>{service['name']}</td>
                    <td>{service['count']}</td>
                </tr>
                '''
        else:
            summary_html = '''
            <tr>
                <td colspan="2" style="text-align: center; color: var(--text-muted);">Tidak ada services yang ditemukan.</td>
            </tr>
            '''
        
        return summary_html
    
    def generate_html_report(self):
        """Generate HTML report dari template"""
        print("\n📄 Generating HTML report...")
        
        # Load template
        with open('templates/report_template.html', 'r', encoding='utf-8') as f:
            template = f.read()
        
        # Calculate summary data
        total_services = len([k for k, v in self.assessment_data['services'].items() if v.get('count', 0) > 0])
        total_resources = sum(v.get('count', 0) for v in self.assessment_data['services'].values())
        
        # Calculate total monthly cost from billing data (bulan lalu)
        total_monthly_cost = 0
        
        if self.assessment_data['billing_data'] and 'monthly_costs' in self.assessment_data['billing_data']:
            monthly_costs = self.assessment_data['billing_data']['monthly_costs']
            if monthly_costs:
                total_monthly_cost = monthly_costs[-1]['total']
        
        # Replace basic placeholders
        replacements = {
            '{{CUSTOMER_NAME}}': self.customer_name,
            '{{ACCOUNT_ID}}': self.account_id,
            '{{ASSESSMENT_DATE}}': datetime.now().strftime('%d %B %Y'),
            '{{AWS_REGION}}': self.region,
            '{{SERVICES_COUNT}}': str(total_services),
            '{{RESOURCES_COUNT}}': str(total_resources),
            '{{TOTAL_MONTHLY_COST}}': f'${total_monthly_cost:,.2f}' if total_monthly_cost > 0 else '$0.00',
            '{{GENERATION_TIMESTAMP}}': datetime.now().strftime('%d %B %Y, %H:%M:%S')
        }
        
        for placeholder, value in replacements.items():
            template = template.replace(placeholder, value)
        
        # Generate Top Cost Drivers table
        top_drivers_html = ''
        if self.assessment_data['billing_data'] and 'top_services' in self.assessment_data['billing_data']:
            top_services = self.assessment_data['billing_data']['top_services'][:10]
            for service, cost in top_services:
                percentage = (cost / total_monthly_cost * 100) if total_monthly_cost > 0 else 0
                top_drivers_html += f'''
                <tr>
                    <td>{service}</td>
                    <td>${cost:,.2f}</td>
                    <td>{percentage:.1f}%</td>
                </tr>
                '''
        else:
            top_drivers_html = '''
            <tr>
                <td colspan="3" style="text-align: center; color: var(--text-muted);">Data billing tidak tersedia. Aktifkan Cost Explorer untuk melihat breakdown biaya.</td>
            </tr>
            '''
        template = template.replace('{{TOP_COST_DRIVERS}}', top_drivers_html)
        
        # Generate Summary Services table
        summary_services_html = self._generate_summary_services()
        template = template.replace('{{SUMMARY_SERVICES}}', summary_services_html)
        
        # Generate Services Inventory - Dinamis untuk semua services
        services_html = self._generate_services_inventory()
        template = template.replace('{{SERVICES_INVENTORY_CONTENT}}', services_html)
        
        # Save HTML report
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"output/assessment_report_{timestamp}.html"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(template)
        
        print(f"✓ HTML report generated: {output_file}")
        return output_file
    
    def generate_pdf_report(self, html_file):
        """Generate PDF report dari HTML file"""
        print("\n📄 Generating PDF report...")
        
        try:
            import pdfkit
            import os
            import platform
            
            # Konfigurasi path wkhtmltopdf untuk Windows
            config = None
            if platform.system() == 'Windows':
                # Coba beberapa lokasi umum instalasi wkhtmltopdf di Windows
                possible_paths = [
                    r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe',
                    r'C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe',
                    os.path.join(os.environ.get('PROGRAMFILES', 'C:\\Program Files'), 'wkhtmltopdf', 'bin', 'wkhtmltopdf.exe'),
                    os.path.join(os.environ.get('PROGRAMFILES(X86)', 'C:\\Program Files (x86)'), 'wkhtmltopdf', 'bin', 'wkhtmltopdf.exe'),
                ]
                
                wkhtmltopdf_path = None
                for path in possible_paths:
                    if os.path.exists(path):
                        wkhtmltopdf_path = path
                        print(f"  ✓ Found wkhtmltopdf at: {path}")
                        break
                
                if wkhtmltopdf_path:
                    config = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)
                else:
                    print("  ⚠ wkhtmltopdf tidak ditemukan di lokasi default.")
                    print("  Mencoba menggunakan PATH system...")
            
            # PDF options untuk hasil yang optimal
            options = {
                'page-size': 'A4',
                'orientation': 'Portrait',
                'margin-top': '1.5cm',
                'margin-right': '1cm',
                'margin-bottom': '1.5cm',
                'margin-left': '1cm',
                'encoding': 'UTF-8',
                'no-outline': None,
                'enable-local-file-access': None,
                'print-media-type': None,
                'footer-center': 'Page [page] of [topage]',
                'footer-font-size': '9',
                'footer-spacing': '5',
                'header-center': 'AWS Account Assessment Report',
                'header-font-size': '9',
                'header-spacing': '5'
            }
            
            # Generate PDF filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            pdf_file = f"output/assessment_report_{timestamp}.pdf"
            
            # Convert HTML to PDF
            if config:
                pdfkit.from_file(html_file, pdf_file, options=options, configuration=config)
            else:
                pdfkit.from_file(html_file, pdf_file, options=options)
            
            print(f"✓ PDF report generated: {pdf_file}")
            return pdf_file
            
        except ImportError:
            print("⚠ pdfkit tidak terinstall. Install dengan: pip install pdfkit")
            print("  Anda juga perlu install wkhtmltopdf:")
            print("  - Windows: Download dari https://wkhtmltopdf.org/downloads.html")
            print("  - macOS: brew install wkhtmltopdf")
            print("  - Linux: sudo apt-get install wkhtmltopdf")
            print("  PDF report tidak dapat di-generate, hanya HTML yang tersedia.")
            return None
        except OSError as e:
            if 'wkhtmltopdf' in str(e) or 'No wkhtmltopdf' in str(e):
                print("⚠ wkhtmltopdf tidak ditemukan di system.")
                print("  Lokasi yang sudah dicek:")
                print("  - C:\\Program Files\\wkhtmltopdf\\bin\\wkhtmltopdf.exe")
                print("  - C:\\Program Files (x86)\\wkhtmltopdf\\bin\\wkhtmltopdf.exe")
                print("  ")
                print("  Solusi:")
                print("  1. Pastikan wkhtmltopdf sudah terinstall")
                print("  2. Tambahkan ke PATH: C:\\Program Files\\wkhtmltopdf\\bin")
                print("  3. Atau install ulang dari: https://wkhtmltopdf.org/downloads.html")
                print("  4. Restart terminal setelah install")
                print("  ")
                print("  PDF report tidak dapat di-generate, hanya HTML yang tersedia.")
            else:
                print(f"✗ Error generating PDF: {str(e)}")
                print("  PDF report tidak dapat di-generate, hanya HTML yang tersedia.")
            return None
        except Exception as e:
            print(f"✗ Error generating PDF: {str(e)}")
            print("  PDF report tidak dapat di-generate, hanya HTML yang tersedia.")
            return None

def main():
    """Main function"""
    try:
        assessment = AWSAssessment()
        
        if assessment.run_assessment():
            html_file = assessment.generate_html_report()
            assessment.generate_pdf_report(html_file)
            print("\n✅ Assessment completed successfully!")
        else:
            print("\n❌ Assessment failed!")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
