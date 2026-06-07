def inventory_s3(session, assessment_data):
    """Inventory S3 buckets"""
    print("\n🪣 Inventarisasi S3 buckets...")
    try:
        from botocore.exceptions import ClientError
        s3 = session.client('s3')

        buckets = s3.list_buckets()
        bucket_list = []

        for bucket in buckets['Buckets']:
            name = bucket['Name']

            # Lifecycle
            try:
                lc = s3.get_bucket_lifecycle_configuration(Bucket=name)
                has_lifecycle = len(lc.get('Rules', [])) > 0
            except ClientError as e:
                has_lifecycle = False if e.response['Error']['Code'] == 'NoSuchLifecycleConfiguration' else None

            # Versioning
            try:
                ver = s3.get_bucket_versioning(Bucket=name)
                versioning_status = ver.get('Status', 'Never') or 'Never'
            except ClientError:
                versioning_status = None

            # Encryption
            try:
                s3.get_bucket_encryption(Bucket=name)
                encrypted = True
            except ClientError:
                encrypted = False

            bucket_list.append({
                'name':               name,
                'creation_date':      bucket['CreationDate'].strftime('%Y-%m-%d %H:%M:%S'),
                'has_lifecycle':      has_lifecycle,
                'versioning_status':  versioning_status,
                'encrypted':          encrypted,
            })

        assessment_data['services']['s3'] = {
            'count':   len(bucket_list),
            'buckets': bucket_list,
        }

        print(f"✓ Found {len(bucket_list)} S3 buckets")
        return True
    except Exception as e:
        print(f"✗ Error inventorying S3: {str(e)}")
        return False

def inventory_ebs(session, assessment_data):
    """Inventory EBS volumes"""
    print("\n💾 Inventarisasi EBS volumes...")
    try:
        ec2 = session.client('ec2')
        paginator = ec2.get_paginator('describe_volumes')

        volume_list = []
        for page in paginator.paginate():
            for volume in page.get('Volumes', []):
                # Ambil instance yang attach (untuk cost optimization rule)
                attachments = volume.get('Attachments', [])
                attached_instance = attachments[0]['InstanceId'] if attachments else None

                volume_list.append({
                    'id':                volume['VolumeId'],
                    'size':              volume['Size'],
                    'type':              volume['VolumeType'],
                    'state':             volume['State'],
                    'iops':              volume.get('Iops', 'N/A'),
                    'encrypted':         volume.get('Encrypted', False),
                    'attached_instance': attached_instance,
                    'throughput':        volume.get('Throughput', None),
                    'name':              next((t['Value'] for t in volume.get('Tags', []) if t['Key'] == 'Name'), ''),
                    'snapshot_id':       volume.get('SnapshotId', ''),
                })

        assessment_data['services']['ebs'] = {
            'count':   len(volume_list),
            'volumes': volume_list,
        }

        print(f"✓ Found {len(volume_list)} EBS volumes")
        return True
    except Exception as e:
        print(f"✗ Error inventorying EBS: {str(e)}")
        return False

def inventory_efs(session, assessment_data):
    """Inventory EFS file systems"""
    print("\n📁 Inventarisasi EFS file systems...")
    try:
        efs = session.client('efs')
        
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
        
        assessment_data['services']['efs'] = {
            'count': len(fs_list),
            'file_systems': fs_list
        }
        
        print(f"✓ Found {len(fs_list)} EFS file systems")
        return True
    except Exception as e:
        print(f"✗ Error inventorying EFS: {str(e)}")
        return False

def inventory_backup(session, assessment_data):
    """Inventory AWS Backup vaults and plans"""
    print("\n💾 Inventarisasi AWS Backup...")
    try:
        backup = session.client('backup')
        
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
        
        assessment_data['services']['backup'] = {
            'count': len(vault_list) + len(plan_list),
            'vaults': vault_list,
            'plans': plan_list
        }
        
        print(f"✓ Found {len(vault_list)} backup vaults and {len(plan_list)} backup plans")
        return True
    except Exception as e:
        print(f"✗ Error inventorying AWS Backup: {str(e)}")
        return False
