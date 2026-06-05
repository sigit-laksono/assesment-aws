import os
from datetime import datetime

def _generate_services_inventory(assessment_data):
    """Generate HTML untuk services inventory secara dinamis"""
    services_html = ''
    
    # EC2 Section
    if 'ec2' in assessment_data['services']:
        ec2_data = assessment_data['services']['ec2']
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
    if 's3' in assessment_data['services']:
        s3_data = assessment_data['services']['s3']
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
    if 'rds' in assessment_data['services']:
        rds_data = assessment_data['services']['rds']
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
    if 'lambda' in assessment_data['services']:
        lambda_data = assessment_data['services']['lambda']
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
    if 'dynamodb' in assessment_data['services']:
        dynamodb_data = assessment_data['services']['dynamodb']
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
    if 'cloudfront' in assessment_data['services']:
        cf_data = assessment_data['services']['cloudfront']
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

    # EKS Section
    if 'eks' in assessment_data['services']:
        eks_data = assessment_data['services']['eks']
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
    if 'ebs' in assessment_data['services']:
        ebs_data = assessment_data['services']['ebs']
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
    if 'elasticache' in assessment_data['services']:
        ec_data = assessment_data['services']['elasticache']
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
    if 'vpc' in assessment_data['services']:
        vpc_data = assessment_data['services']['vpc']
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
    if 'nat_gateway' in assessment_data['services']:
        nat_data = assessment_data['services']['nat_gateway']
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
    if 'kms' in assessment_data['services']:
        kms_data = assessment_data['services']['kms']
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
    if 'waf' in assessment_data['services']:
        waf_data = assessment_data['services']['waf']
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
    if 'cloudwatch' in assessment_data['services']:
        cw_data = assessment_data['services']['cloudwatch']
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
    if 'cloudtrail' in assessment_data['services']:
        ct_data = assessment_data['services']['cloudtrail']
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
    if 'config' in assessment_data['services']:
        config_data = assessment_data['services']['config']
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
    if 'efs' in assessment_data['services']:
        efs_data = assessment_data['services']['efs']
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
    if 'backup' in assessment_data['services']:
        backup_data = assessment_data['services']['backup']
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
    if 'alb' in assessment_data['services']:
        alb_data = assessment_data['services']['alb']
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
    if 'secretsmanager' in assessment_data['services']:
        sm_data = assessment_data['services']['secretsmanager']
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
    if 'sns' in assessment_data['services']:
        sns_data = assessment_data['services']['sns']
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
    if 'msk' in assessment_data['services']:
        msk_data = assessment_data['services']['msk']
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
    if 'amazonmq' in assessment_data['services']:
        mq_data = assessment_data['services']['amazonmq']
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
    if 'glue' in assessment_data['services']:
        glue_data = assessment_data['services']['glue']
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
    
    # ECR Section
    if 'ecr' in assessment_data['services']:
        ecr_data = assessment_data['services']['ecr']
        if ecr_data.get('count', 0) > 0:
            services_html += f'''
            <h3>ECR - Elastic Container Registry</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>Repository Name</th>
                            <th>URI</th>
                            <th>Images</th>
                            <th>Tag Mutability</th>
                            <th>Scan on Push</th>
                            <th>Created</th>
                        </tr>
                    </thead>
                    <tbody>
            '''
            for repo in ecr_data['repositories']:
                services_html += f'''
                <tr>
                    <td>{repo['name']}</td>
                    <td>{repo['uri']}</td>
                    <td>{repo['image_count']}</td>
                    <td>{repo['image_tag_mutability']}</td>
                    <td>{'Yes' if repo['scan_on_push'] else 'No'}</td>
                    <td>{repo['created_at']}</td>
                </tr>
                '''
            services_html += '</tbody></table></div>'

    # Route 53 Section
    if 'route53' in assessment_data['services']:
        r53_data = assessment_data['services']['route53']
        if r53_data.get('count', 0) > 0:
            services_html += f'''
            <h3>Route 53 - DNS Service</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>Zone ID</th>
                            <th>Domain Name</th>
                            <th>Type</th>
                            <th>Record Count</th>
                            <th>Comment</th>
                        </tr>
                    </thead>
                    <tbody>
            '''
            for zone in r53_data['hosted_zones']:
                services_html += f'''
                <tr>
                    <td>{zone['id']}</td>
                    <td>{zone['name']}</td>
                    <td>{zone['type']}</td>
                    <td>{zone['record_count']}</td>
                    <td>{zone['comment']}</td>
                </tr>
                '''
            services_html += '</tbody></table></div>'

    # NLB Section
    if 'nlb' in assessment_data['services']:
        nlb_data = assessment_data['services']['nlb']
        if nlb_data.get('count', 0) > 0:
            services_html += f'''
            <h3>NLB - Network Load Balancer</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>Name</th>
                            <th>DNS Name</th>
                            <th>Scheme</th>
                            <th>State</th>
                            <th>VPC ID</th>
                        </tr>
                    </thead>
                    <tbody>
            '''
            for lb in nlb_data['load_balancers']:
                services_html += f'''
                <tr>
                    <td>{lb['name']}</td>
                    <td>{lb['dns']}</td>
                    <td>{lb['scheme']}</td>
                    <td>{lb['state']}</td>
                    <td>{lb['vpc_id']}</td>
                </tr>
                '''
            services_html += '</tbody></table></div>'

    if not services_html:
        services_html = '<p style="color: var(--text-muted); text-align: center; padding: 40px;">Tidak ada services yang ditemukan.</p>'
    
    return services_html

def _generate_summary_services(assessment_data):
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
        'glue': 'AWS Glue',
        'ecr': 'ECR (Container Registry)',
        'route53': 'Route 53',
        'nlb': 'NLB (Network Load Balancer)'
    }
    
    # Collect all services with their counts
    services_summary = []
    for service_key, service_data in assessment_data['services'].items():
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

def _generate_security_findings(assessment_data):
    """Generate HTML untuk Security Findings section"""
    findings = assessment_data.get('security_findings', [])

    if not findings:
        return '''
        <div class="empty-state">
            <p>✅ Tidak ditemukan security finding dari rule yang dijalankan.</p>
            <p style="color: var(--text-muted); font-size: 0.9em;">
                Catatan: Rule yang dievaluasi saat ini adalah EBS unencrypted dan
                CloudTrail multi-region. Rule tambahan akan ditambahkan di rilis berikutnya.
            </p>
        </div>
        '''

    # Hitung ringkasan per severity
    sev_order = ['critical', 'high', 'medium', 'low']
    sev_count = {s: 0 for s in sev_order}
    for f in findings:
        sev_count[f['severity']] = sev_count.get(f['severity'], 0) + 1

    badges_html = ''.join(
        f'<span class="severity-badge {s}">{sev_count[s]} {s.title()}</span>'
        for s in sev_order if sev_count[s] > 0
    )

    rows_html = ''
    # Urutkan: critical -> high -> medium -> low
    sev_rank = {s: i for i, s in enumerate(sev_order)}
    sorted_findings = sorted(findings, key=lambda x: sev_rank.get(x['severity'], 99))

    for f in sorted_findings:
        rows_html += f'''
        <tr>
            <td>{f['id']}</td>
            <td><span class="severity-badge {f['severity']}">{f['severity'].title()}</span></td>
            <td>{f['service']}</td>
            <td>{f['resource_id']}</td>
            <td>
                <strong>{f['title']}</strong><br>
                <span style="color: var(--text-muted); font-size: 0.9em;">{f['description']}</span><br>
                <span style="font-size: 0.9em;"><strong>Rekomendasi:</strong> {f['recommendation']}</span>
            </td>
        </tr>
        '''

    return f'''
    <div class="service-detail-card">
        <div class="service-summary-stats">
            <div class="stat-item">
                <div class="stat-label">Total Findings</div>
                <div class="stat-value">{len(findings)}</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Severity Breakdown</div>
                <div class="stat-badges">{badges_html}</div>
            </div>
        </div>
        <div class="table-wrapper">
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Severity</th>
                        <th>Service</th>
                        <th>Resource</th>
                        <th>Detail & Rekomendasi</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>
    </div>
    '''


def generate_html_report(assessment_data, customer_name, account_id, region):
    """Generate HTML report dari template"""
    print("\n📄 Generating HTML report...")
    
    # Load template
    template_path = 'templates/report_template.html'
    if not os.path.exists(template_path):
        # Fallback to local templates folder if running from different cwd
        template_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'report_template.html')

    with open(template_path, 'r', encoding='utf-8') as f:
        template = f.read()
    
    # Calculate summary data
    total_services = len([k for k, v in assessment_data['services'].items() if v.get('count', 0) > 0])
    total_resources = sum(v.get('count', 0) for v in assessment_data['services'].values())
    
    # Calculate total monthly cost from billing data (bulan lalu)
    total_monthly_cost = 0
    if assessment_data['billing_data'] and 'monthly_costs' in assessment_data['billing_data']:
        monthly_costs = assessment_data['billing_data']['monthly_costs']
        if monthly_costs:
            total_monthly_cost = monthly_costs[-1]['total']
    
    # Load static assets (CSS & JS)
    styles_path = 'templates/report_styles.css'
    scripts_path = 'templates/report_scripts.js'
    
    # Fallback paths
    if not os.path.exists(styles_path):
        styles_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'report_styles.css')
    if not os.path.exists(scripts_path):
        scripts_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'report_scripts.js')
        
    report_styles = ""
    if os.path.exists(styles_path):
        with open(styles_path, 'r', encoding='utf-8') as f:
            report_styles = f.read()
            
    report_scripts = ""
    if os.path.exists(scripts_path):
        with open(scripts_path, 'r', encoding='utf-8') as f:
            report_scripts = f.read()

    # Replace basic placeholders
    replacements = {
        '{{CUSTOMER_NAME}}': customer_name,
        '{{ACCOUNT_ID}}': account_id,
        '{{ASSESSMENT_DATE}}': datetime.now().strftime('%d %B %Y'),
        '{{AWS_REGION}}': region,
        '{{SERVICES_COUNT}}': str(total_services),
        '{{RESOURCES_COUNT}}': str(total_resources),
        '{{TOTAL_MONTHLY_COST}}': f'${total_monthly_cost:,.2f}' if total_monthly_cost > 0 else '$0.00',
        '{{GENERATION_TIMESTAMP}}': datetime.now().strftime('%d %B %Y, %H:%M:%S'),
        '/* __REPORT_STYLES__ */': report_styles,
        '/* __REPORT_SCRIPTS__ */': report_scripts
    }
    
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)
    
    # Generate Top Cost Drivers table
    top_drivers_html = ''
    if assessment_data['billing_data'] and 'top_services' in assessment_data['billing_data']:
        top_services = assessment_data['billing_data']['top_services'][:10]
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
    summary_services_html = _generate_summary_services(assessment_data)
    template = template.replace('{{SUMMARY_SERVICES}}', summary_services_html)
    
    # Generate Services Inventory - Dinamis untuk semua services
    services_html = _generate_services_inventory(assessment_data)
    template = template.replace('{{SERVICES_INVENTORY_CONTENT}}', services_html)

    # Generate Security Findings section
    security_html = _generate_security_findings(assessment_data)
    template = template.replace('{{SECURITY_FINDINGS}}', security_html)
    
    # Save HTML report
    os.makedirs('output', exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = f"output/assessment_report_{timestamp}.html"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(template)
    
    print(f"✓ HTML report generated: {output_file}")
    return output_file

def generate_pdf_report(html_file):
    """Generate PDF report dari HTML file menggunakan Playwright (Headless Chrome)"""
    print("\n📄 Generating PDF report...")
    
    try:
        import asyncio
        from playwright.sync_api import sync_playwright
        
        # Generate PDF filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        pdf_file = f"output/assessment_report_{timestamp}.pdf"
        
        # Ambil path absolut file HTML (Playwright butuh absolute path dengan file:// prefix)
        abs_html_path = f"file://{os.path.abspath(html_file)}"
        
        with sync_playwright() as p:
            # Gunakan chromium (engine chrome)
            browser = p.chromium.launch()
            page = browser.new_page()
            
            # Buka file HTML
            page.goto(abs_html_path)
            
            # Berikan waktu sejenak agar JavaScript (Chart.js & Sidebar builder) selesai render
            print("  - Waiting for content to render...")
            page.wait_for_timeout(2000) 
            
            # Force show all rows and elements before generating PDF
            print("  - Disabling pagination and filters for PDF...")
            page.evaluate("""
                // Show all rows
                document.querySelectorAll('tr').forEach(tr => {
                    tr.classList.remove('page-hidden');
                    tr.classList.remove('filtered-hidden');
                });
                // Ensure all service sections are visible
                document.querySelectorAll('.table-wrapper, .service-detail-card, h3').forEach(el => {
                    el.classList.remove('filtered-hidden');
                });
            """)
            
            # Generate PDF
            page.pdf(
                path=pdf_file,
                format="A4",
                print_background=True,
                margin={
                    "top": "1cm",
                    "right": "1cm",
                    "bottom": "1cm",
                    "left": "1cm"
                },
                display_header_footer=True,
                header_template='<div style="font-size: 10px; width: 100%; text-align: center; color: #666;">AWS Account Assessment Report</div>',
                footer_template='<div style="font-size: 10px; width: 100%; text-align: center; color: #666;">Page <span class="pageNumber"></span> / <span class="totalPages"></span></div>'
            )
            
            browser.close()
            
        print(f"✓ PDF report generated: {pdf_file}")
        return pdf_file

    except ImportError:
        print("⚠ playwright tidak terinstall. Jalankan:")
        print("  pip install playwright")
        print("  playwright install chromium")
        return None
    except Exception as e:
        print(f"✗ Error generating PDF: {str(e)}")
        return None
