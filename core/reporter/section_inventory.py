"""
Section: Services Inventory
Render tabel HTML untuk setiap AWS service yang dikumpulkan.
"""


def generate_services_inventory(assessment_data: dict) -> str:
    """Generate HTML untuk services inventory secara dinamis."""
    services_html = ''

    # ── EC2 ───────────────────────────────────────────────────────────────────
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
                                <th>Name</th>
                                <th>Instance ID</th>
                                <th>Type</th>
                                <th>Platform</th>
                                <th>Architecture</th>
                                <th>AZ</th>
                                <th>Public IP</th>
                                <th>State</th>
                                <th>Launch Time</th>
                            </tr>
                        </thead>
                        <tbody>
            '''
            for instance in ec2_data['instances']:
                state_class = 'running' if instance['state'] == 'running' else 'stopped'
                name = instance.get('name') or '-'
                platform = instance.get('platform', 'Linux')
                platform_class = 'windows' if platform.lower() == 'windows' else 'linux'
                arch = instance.get('architecture', '-')
                az = instance.get('availability_zone', '-')
                az_short = az[-2:] if az and len(az) > 2 else az
                public_ip = instance.get('public_ip') or '-'
                services_html += f'''
                <tr>
                    <td>{name}</td>
                    <td>{instance['id']}</td>
                    <td>{instance['type']}</td>
                    <td><span class="platform-badge {platform_class}">{platform}</span></td>
                    <td>{arch}</td>
                    <td>{az_short}</td>
                    <td>{public_ip}</td>
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

    # ── S3 ────────────────────────────────────────────────────────────────────
    if 's3' in assessment_data['services']:
        s3_data = assessment_data['services']['s3']
        if s3_data.get('count', 0) > 0:
            services_html += f'''
            <h3>S3 - Simple Storage Service</h3>
            <div class="table-wrapper">
                <table>
                    <thead><tr><th>Bucket Name</th><th>Creation Date</th></tr></thead>
                    <tbody>
            '''
            for bucket in s3_data['buckets']:
                services_html += f'''
                <tr>
                    <td>{bucket['name']}</td>
                    <td>{bucket['creation_date']}</td>
                </tr>'''
            services_html += '</tbody></table></div>'

    # ── RDS ───────────────────────────────────────────────────────────────────
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
                                <th>Instance ID</th><th>Engine</th><th>Version</th>
                                <th>Class</th><th>Status</th><th>Multi-AZ</th>
                                <th>Encrypted</th><th>Backup (days)</th>
                                <th>Public</th><th>Deletion Protection</th>
                            </tr>
                        </thead>
                        <tbody>
            '''
            _yes = '<span style="color:#16a34a;font-weight:600;">✓</span>'
            _no  = '<span style="color:#dc2626;font-weight:600;">✗</span>'
            for instance in rds_data['instances']:
                status_class = 'available' if instance['status'] == 'available' else 'inactive'
                services_html += f'''
                <tr>
                    <td>{instance['id']}</td>
                    <td>{instance['engine']}</td>
                    <td>{instance.get('engine_version', '-')}</td>
                    <td>{instance['class']}</td>
                    <td><span class="status-badge {status_class}">{instance['status'].title()}</span></td>
                    <td>{_yes if instance.get('multi_az', False) else _no}</td>
                    <td>{_yes if instance.get('storage_encrypted', False) else _no}</td>
                    <td>{instance.get('backup_retention', 0)}</td>
                    <td>{_yes if instance.get('publicly_accessible', False) else _no}</td>
                    <td>{_yes if instance.get('deletion_protection', False) else _no}</td>
                </tr>'''
            services_html += '''
                        </tbody></table></div>
                <div class="pagination" id="rds-pagination"></div>
            </div>'''

    # ── Lambda ────────────────────────────────────────────────────────────────
    if 'lambda' in assessment_data['services']:
        lambda_data = assessment_data['services']['lambda']
        if lambda_data.get('count', 0) > 0:
            services_html += f'''
            <h3>Lambda - Serverless Functions</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>Function Name</th><th>Runtime</th>
                            <th>Memory (MB)</th><th>Last Modified</th>
                        </tr>
                    </thead>
                    <tbody>
            '''
            for func in lambda_data['functions']:
                services_html += f'''
                <tr>
                    <td>{func['name']}</td><td>{func['runtime']}</td>
                    <td>{func['memory']}</td><td>{func['last_modified']}</td>
                </tr>'''
            services_html += '</tbody></table></div>'

    # ── DynamoDB ──────────────────────────────────────────────────────────────
    if 'dynamodb' in assessment_data['services']:
        dynamodb_data = assessment_data['services']['dynamodb']
        if dynamodb_data.get('count', 0) > 0:
            services_html += f'''
            <h3>DynamoDB - NoSQL Database</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>Table Name</th><th>Status</th>
                            <th>Item Count</th><th>Size (Bytes)</th>
                        </tr>
                    </thead>
                    <tbody>
            '''
            for table in dynamodb_data['tables']:
                services_html += f'''
                <tr>
                    <td>{table['name']}</td><td>{table['status']}</td>
                    <td>{table['item_count']:,}</td><td>{table['size_bytes']:,}</td>
                </tr>'''
            services_html += '</tbody></table></div>'

    # ── CloudFront ────────────────────────────────────────────────────────────
    if 'cloudfront' in assessment_data['services']:
        cf_data = assessment_data['services']['cloudfront']
        if cf_data.get('count', 0) > 0:
            services_html += f'''
            <h3>CloudFront - Content Delivery Network</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>Distribution ID</th><th>Domain Name</th>
                            <th>Status</th><th>Enabled</th>
                        </tr>
                    </thead>
                    <tbody>
            '''
            for dist in cf_data['distributions']:
                services_html += f'''
                <tr>
                    <td>{dist['id']}</td><td>{dist['domain']}</td>
                    <td>{dist['status']}</td><td>{'Yes' if dist['enabled'] else 'No'}</td>
                </tr>'''
            services_html += '</tbody></table></div>'

    # ── EKS ───────────────────────────────────────────────────────────────────
    if 'eks' in assessment_data['services']:
        eks_data = assessment_data['services']['eks']
        if eks_data.get('count', 0) > 0:
            services_html += f'''
            <h3>EKS - Elastic Kubernetes Service</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>Cluster Name</th><th>Status</th>
                            <th>Version</th><th>Created At</th>
                        </tr>
                    </thead>
                    <tbody>
            '''
            for cluster in eks_data['clusters']:
                services_html += f'''
                <tr>
                    <td>{cluster['name']}</td><td>{cluster['status']}</td>
                    <td>{cluster['version']}</td><td>{cluster['created_at']}</td>
                </tr>'''
            services_html += '</tbody></table></div>'

    # ── EBS ───────────────────────────────────────────────────────────────────
    if 'ebs' in assessment_data['services']:
        ebs_data = assessment_data['services']['ebs']
        if ebs_data.get('count', 0) > 0:
            services_html += f'''
            <h3>EBS - Elastic Block Store</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>Volume ID</th><th>Size (GB)</th>
                            <th>Type</th><th>State</th><th>Encrypted</th>
                        </tr>
                    </thead>
                    <tbody>
            '''
            for volume in ebs_data['volumes']:
                services_html += f'''
                <tr>
                    <td>{volume['id']}</td><td>{volume['size']}</td>
                    <td>{volume['type']}</td><td>{volume['state']}</td>
                    <td>{'Yes' if volume['encrypted'] else 'No'}</td>
                </tr>'''
            services_html += '</tbody></table></div>'

    # ── ElastiCache ───────────────────────────────────────────────────────────
    if 'elasticache' in assessment_data['services']:
        ec_data = assessment_data['services']['elasticache']
        if ec_data.get('count', 0) > 0:
            services_html += f'''
            <h3>ElastiCache - In-Memory Cache</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>Cluster ID</th><th>Engine</th>
                            <th>Node Type</th><th>Nodes</th><th>Status</th>
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
                </tr>'''
            services_html += '</tbody></table></div>'

    # ── VPC ───────────────────────────────────────────────────────────────────
    if 'vpc' in assessment_data['services']:
        vpc_data = assessment_data['services']['vpc']
        if vpc_data.get('count', 0) > 0:
            services_html += f'''
            <h3>VPC - Virtual Private Cloud</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>VPC ID</th><th>Name</th><th>CIDR Block</th>
                            <th>Default</th><th>State</th>
                        </tr>
                    </thead>
                    <tbody>
            '''
            for vpc in vpc_data['vpcs']:
                services_html += f'''
                <tr>
                    <td>{vpc['id']}</td><td>{vpc['name']}</td>
                    <td>{vpc['cidr']}</td>
                    <td>{'Yes' if vpc['is_default'] else 'No'}</td>
                    <td>{vpc['state']}</td>
                </tr>'''
            services_html += '</tbody></table></div>'

    # ── NAT Gateway ───────────────────────────────────────────────────────────
    if 'nat_gateway' in assessment_data['services']:
        nat_data = assessment_data['services']['nat_gateway']
        if nat_data.get('count', 0) > 0:
            services_html += f'''
            <h3>NAT Gateway</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>NAT Gateway ID</th><th>VPC ID</th>
                            <th>Subnet ID</th><th>State</th>
                        </tr>
                    </thead>
                    <tbody>
            '''
            for nat in nat_data['nat_gateways']:
                services_html += f'''
                <tr>
                    <td>{nat['id']}</td><td>{nat['vpc_id']}</td>
                    <td>{nat['subnet_id']}</td><td>{nat['state']}</td>
                </tr>'''
            services_html += '</tbody></table></div>'

    # ── IAM ───────────────────────────────────────────────────────────────────
    if 'iam' in assessment_data['services']:
        iam_data = assessment_data['services']['iam']
        root_mfa  = iam_data.get('root_mfa_enabled', False)
        pwd_policy = iam_data.get('password_policy_set', False)
        root_mfa_badge  = ('<span style="color:#16a34a;">✓ Enabled</span>' if root_mfa
                           else '<span style="color:#dc2626;font-weight:600;">✗ DISABLED</span>')
        pwd_policy_badge = ('<span style="color:#16a34a;">✓ Set</span>' if pwd_policy
                            else '<span style="color:#dc2626;font-weight:600;">✗ Not Set</span>')
        services_html += f'''
        <h3>IAM - Identity and Access Management</h3>
        <div class="table-wrapper">
            <table>
                <thead><tr><th>Metric</th><th>Value</th></tr></thead>
                <tbody>
                    <tr><td>Users</td><td>{iam_data.get('users_count', 0)}</td></tr>
                    <tr><td>Groups</td><td>{iam_data.get('groups_count', 0)}</td></tr>
                    <tr><td>Roles</td><td>{iam_data.get('roles_count', 0)}</td></tr>
                    <tr><td>Customer Managed Policies</td><td>{iam_data.get('policies_count', 0)}</td></tr>
                    <tr><td>MFA Devices In Use</td><td>{iam_data.get('mfa_devices_in_use', 0)}</td></tr>
                    <tr><td>Root MFA</td><td>{root_mfa_badge}</td></tr>
                    <tr><td>Password Policy</td><td>{pwd_policy_badge}</td></tr>
                    <tr><td>Min Password Length</td><td>{iam_data.get('min_password_length', 0) or 'N/A'}</td></tr>
                    <tr><td>Password Reuse Prevention</td><td>{iam_data.get('password_reuse_prevention', 0) or 'N/A'}</td></tr>
                    <tr><td>Max Password Age (days)</td><td>{iam_data.get('max_password_age', 0) or 'N/A'}</td></tr>
                </tbody>
            </table>
        </div>'''

    # ── KMS ───────────────────────────────────────────────────────────────────
    if 'kms' in assessment_data['services']:
        kms_data = assessment_data['services']['kms']
        if kms_data.get('count', 0) > 0:
            services_html += f'''
            <h3>KMS - Key Management Service</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>Key ID</th><th>State</th>
                            <th>Enabled</th><th>Created Date</th>
                        </tr>
                    </thead>
                    <tbody>
            '''
            for key in kms_data['keys']:
                services_html += f'''
                <tr>
                    <td>{key['id']}</td><td>{key['state']}</td>
                    <td>{'Yes' if key['enabled'] else 'No'}</td>
                    <td>{key['created_date']}</td>
                </tr>'''
            services_html += '</tbody></table></div>'

    # ── WAF ───────────────────────────────────────────────────────────────────
    if 'waf' in assessment_data['services']:
        waf_data = assessment_data['services']['waf']
        if waf_data.get('count', 0) > 0:
            services_html += f'''
            <h3>WAF - Web Application Firewall</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr><th>Web ACL Name</th><th>Scope</th><th>ID</th></tr>
                    </thead>
                    <tbody>
            '''
            for acl in waf_data['web_acls']:
                services_html += f'''
                <tr>
                    <td>{acl['name']}</td><td>{acl['scope']}</td><td>{acl['id']}</td>
                </tr>'''
            services_html += '</tbody></table></div>'

    # ── CloudWatch ────────────────────────────────────────────────────────────
    if 'cloudwatch' in assessment_data['services']:
        cw_data = assessment_data['services']['cloudwatch']
        if cw_data.get('count', 0) > 0:
            services_html += f'''
            <h3>CloudWatch - Monitoring & Alarms</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>Alarm Name</th><th>State</th>
                            <th>Metric</th><th>Namespace</th>
                        </tr>
                    </thead>
                    <tbody>
            '''
            for alarm in cw_data['alarms']:
                services_html += f'''
                <tr>
                    <td>{alarm['name']}</td><td>{alarm['state']}</td>
                    <td>{alarm['metric']}</td><td>{alarm['namespace']}</td>
                </tr>'''
            services_html += '</tbody></table></div>'

    # ── CloudTrail ────────────────────────────────────────────────────────────
    if 'cloudtrail' in assessment_data['services']:
        ct_data = assessment_data['services']['cloudtrail']
        if ct_data.get('count', 0) > 0:
            services_html += f'''
            <h3>CloudTrail - Audit Logging</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>Trail Name</th><th>Logging</th>
                            <th>Multi-Region</th><th>S3 Bucket</th>
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
                </tr>'''
            services_html += '</tbody></table></div>'

    # ── AWS Config ────────────────────────────────────────────────────────────
    if 'config' in assessment_data['services']:
        config_data = assessment_data['services']['config']
        if config_data.get('count', 0) > 0:
            services_html += f'''
            <h3>AWS Config - Configuration Recorder</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>Recorder Name</th><th>Recording</th>
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
                </tr>'''
            services_html += '</tbody></table></div>'

    # ── EFS ───────────────────────────────────────────────────────────────────
    if 'efs' in assessment_data['services']:
        efs_data = assessment_data['services']['efs']
        if efs_data.get('count', 0) > 0:
            services_html += f'''
            <h3>EFS - Elastic File System</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>File System ID</th><th>Name</th><th>State</th>
                            <th>Mount Targets</th><th>Encrypted</th>
                        </tr>
                    </thead>
                    <tbody>
            '''
            for fs in efs_data['file_systems']:
                services_html += f'''
                <tr>
                    <td>{fs['id']}</td><td>{fs['name']}</td>
                    <td>{fs['life_cycle_state']}</td>
                    <td>{fs['number_of_mount_targets']}</td>
                    <td>{'Yes' if fs['encrypted'] else 'No'}</td>
                </tr>'''
            services_html += '</tbody></table></div>'

    # ── AWS Backup ────────────────────────────────────────────────────────────
    if 'backup' in assessment_data['services']:
        backup_data = assessment_data['services']['backup']
        if backup_data.get('count', 0) > 0:
            services_html += f'''
            <h3>AWS Backup</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr><th>Type</th><th>Name</th><th>Details</th></tr>
                    </thead>
                    <tbody>
            '''
            for vault in backup_data.get('vaults', []):
                services_html += f'''
                <tr>
                    <td>Vault</td><td>{vault['name']}</td>
                    <td>Recovery Points: {vault['number_of_recovery_points']}</td>
                </tr>'''
            for plan in backup_data.get('plans', []):
                services_html += f'''
                <tr>
                    <td>Plan</td><td>{plan['name']}</td>
                    <td>ID: {plan['id']}</td>
                </tr>'''
            services_html += '</tbody></table></div>'

    # ── ALB ───────────────────────────────────────────────────────────────────
    if 'alb' in assessment_data['services']:
        alb_data = assessment_data['services']['alb']
        if alb_data.get('count', 0) > 0:
            services_html += f'''
            <h3>ALB - Application Load Balancer</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>Name</th><th>DNS Name</th>
                            <th>Scheme</th><th>State</th><th>Listeners</th>
                        </tr>
                    </thead>
                    <tbody>
            '''
            for lb in alb_data['load_balancers']:
                listener_count = lb.get('listener_count', '-')
                services_html += f'''
                <tr>
                    <td>{lb['name']}</td><td>{lb['dns']}</td>
                    <td>{lb['scheme']}</td><td>{lb['state']}</td>
                    <td>{listener_count}</td>
                </tr>'''
            services_html += '</tbody></table></div>'

    # ── Secrets Manager ───────────────────────────────────────────────────────
    if 'secretsmanager' in assessment_data['services']:
        sm_data = assessment_data['services']['secretsmanager']
        if sm_data.get('count', 0) > 0:
            services_html += f'''
            <h3>Secrets Manager</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>Secret Name</th><th>Description</th>
                            <th>Rotation Enabled</th><th>Last Changed</th>
                        </tr>
                    </thead>
                    <tbody>
            '''
            for secret in sm_data['secrets']:
                services_html += f'''
                <tr>
                    <td>{secret['name']}</td><td>{secret['description']}</td>
                    <td>{'Yes' if secret['rotation_enabled'] else 'No'}</td>
                    <td>{secret['last_changed_date']}</td>
                </tr>'''
            services_html += '</tbody></table></div>'

    # ── SNS ───────────────────────────────────────────────────────────────────
    if 'sns' in assessment_data['services']:
        sns_data = assessment_data['services']['sns']
        if sns_data.get('count', 0) > 0:
            services_html += f'''
            <h3>SNS - Simple Notification Service</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>Topic Name</th><th>Display Name</th>
                            <th>Subscriptions Confirmed</th><th>Subscriptions Pending</th>
                        </tr>
                    </thead>
                    <tbody>
            '''
            for topic in sns_data['topics']:
                services_html += f'''
                <tr>
                    <td>{topic['name']}</td><td>{topic['display_name']}</td>
                    <td>{topic['subscriptions_confirmed']}</td>
                    <td>{topic['subscriptions_pending']}</td>
                </tr>'''
            services_html += '</tbody></table></div>'

    # ── MSK ───────────────────────────────────────────────────────────────────
    if 'msk' in assessment_data['services']:
        msk_data = assessment_data['services']['msk']
        if msk_data.get('count', 0) > 0:
            services_html += f'''
            <h3>MSK - Managed Streaming for Apache Kafka</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>Cluster Name</th><th>Type</th>
                            <th>State</th><th>Created</th>
                        </tr>
                    </thead>
                    <tbody>
            '''
            for cluster in msk_data['clusters']:
                services_html += f'''
                <tr>
                    <td>{cluster['name']}</td><td>{cluster['cluster_type']}</td>
                    <td>{cluster['state']}</td><td>{cluster['creation_time']}</td>
                </tr>'''
            services_html += '</tbody></table></div>'

    # ── Amazon MQ ─────────────────────────────────────────────────────────────
    if 'amazonmq' in assessment_data['services']:
        mq_data = assessment_data['services']['amazonmq']
        if mq_data.get('count', 0) > 0:
            services_html += f'''
            <h3>Amazon MQ</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>Broker Name</th><th>Engine Type</th>
                            <th>State</th><th>Deployment Mode</th>
                        </tr>
                    </thead>
                    <tbody>
            '''
            for broker in mq_data['brokers']:
                services_html += f'''
                <tr>
                    <td>{broker['name']}</td><td>{broker['engine_type']}</td>
                    <td>{broker['broker_state']}</td><td>{broker['deployment_mode']}</td>
                </tr>'''
            services_html += '</tbody></table></div>'

    # ── AWS Glue ──────────────────────────────────────────────────────────────
    if 'glue' in assessment_data['services']:
        glue_data = assessment_data['services']['glue']
        if glue_data.get('count', 0) > 0:
            services_html += f'''
            <h3>AWS Glue</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr><th>Type</th><th>Name</th><th>Details</th></tr>
                    </thead>
                    <tbody>
            '''
            for db in glue_data.get('databases', []):
                services_html += f'''
                <tr>
                    <td>Database</td><td>{db['name']}</td><td>{db['description']}</td>
                </tr>'''
            for job in glue_data.get('jobs', []):
                services_html += f'''
                <tr>
                    <td>Job</td><td>{job['name']}</td>
                    <td>Glue Version: {job['glue_version']}</td>
                </tr>'''
            services_html += '</tbody></table></div>'

    # ── ECR ───────────────────────────────────────────────────────────────────
    if 'ecr' in assessment_data['services']:
        ecr_data = assessment_data['services']['ecr']
        if ecr_data.get('count', 0) > 0:
            services_html += f'''
            <h3>ECR - Elastic Container Registry</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>Repository Name</th><th>URI</th><th>Images</th>
                            <th>Tag Mutability</th><th>Scan on Push</th><th>Created</th>
                        </tr>
                    </thead>
                    <tbody>
            '''
            for repo in ecr_data['repositories']:
                services_html += f'''
                <tr>
                    <td>{repo['name']}</td><td>{repo['uri']}</td>
                    <td>{repo['image_count']}</td><td>{repo['image_tag_mutability']}</td>
                    <td>{'Yes' if repo['scan_on_push'] else 'No'}</td>
                    <td>{repo['created_at']}</td>
                </tr>'''
            services_html += '</tbody></table></div>'

    # ── Route 53 ──────────────────────────────────────────────────────────────
    if 'route53' in assessment_data['services']:
        r53_data = assessment_data['services']['route53']
        if r53_data.get('count', 0) > 0:
            services_html += f'''
            <h3>Route 53 - DNS Service</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>Zone ID</th><th>Domain Name</th><th>Type</th>
                            <th>Record Count</th><th>Comment</th>
                        </tr>
                    </thead>
                    <tbody>
            '''
            for zone in r53_data['hosted_zones']:
                services_html += f'''
                <tr>
                    <td>{zone['id']}</td><td>{zone['name']}</td>
                    <td>{zone['type']}</td><td>{zone['record_count']}</td>
                    <td>{zone['comment']}</td>
                </tr>'''
            services_html += '</tbody></table></div>'

    # ── NLB ───────────────────────────────────────────────────────────────────
    if 'nlb' in assessment_data['services']:
        nlb_data = assessment_data['services']['nlb']
        if nlb_data.get('count', 0) > 0:
            services_html += f'''
            <h3>NLB - Network Load Balancer</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>Name</th><th>DNS Name</th><th>Scheme</th>
                            <th>State</th><th>VPC ID</th><th>Listeners</th>
                        </tr>
                    </thead>
                    <tbody>
            '''
            for lb in nlb_data['load_balancers']:
                listener_count = lb.get('listener_count', '-')
                services_html += f'''
                <tr>
                    <td>{lb['name']}</td><td>{lb['dns']}</td>
                    <td>{lb['scheme']}</td><td>{lb['state']}</td>
                    <td>{lb['vpc_id']}</td><td>{listener_count}</td>
                </tr>'''
            services_html += '</tbody></table></div>'

    if not services_html:
        services_html = ('<p style="color:var(--text-muted);text-align:center;padding:40px;">'
                         'Tidak ada services yang ditemukan.</p>')

    return services_html
