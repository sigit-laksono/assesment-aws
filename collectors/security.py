def inventory_kms(session, assessment_data):
    """Inventory KMS keys"""
    print("\n🔐 Inventarisasi KMS keys...")
    try:
        kms = session.client('kms')
        
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
        
        assessment_data['services']['kms'] = {
            'count': len(key_list),
            'keys': key_list
        }
        
        print(f"✓ Found {len(key_list)} customer-managed KMS keys")
        return True
    except Exception as e:
        print(f"✗ Error inventorying KMS: {str(e)}")
        return False

def inventory_waf(session, assessment_data):
    """Inventory WAF Web ACLs"""
    print("\n🛡️  Inventarisasi WAF Web ACLs...")
    try:
        wafv2 = session.client('wafv2')
        
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
            wafv2_global = session.client('wafv2', region_name='us-east-1')
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
        
        assessment_data['services']['waf'] = {
            'count': len(acl_list),
            'web_acls': acl_list
        }
        
        print(f"✓ Found {len(acl_list)} WAF Web ACLs")
        return True
    except Exception as e:
        print(f"✗ Error inventorying WAF: {str(e)}")
        return False

def inventory_secretsmanager(session, assessment_data):
    """Inventory Secrets Manager secrets"""
    print("\n🔑 Inventarisasi Secrets Manager...")
    try:
        secretsmanager = session.client('secretsmanager')
        
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
        
        assessment_data['services']['secretsmanager'] = {
            'count': len(secret_list),
            'secrets': secret_list
        }
        
        print(f"✓ Found {len(secret_list)} secrets")
        return True
    except Exception as e:
        print(f"✗ Error inventorying Secrets Manager: {str(e)}")
        return False
