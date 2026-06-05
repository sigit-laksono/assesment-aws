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

def inventory_iam(session, assessment_data):
    """Inventory IAM (summary-level only, no PII)"""
    print("\n👤 Inventarisasi IAM (summary-level)...")
    try:
        iam = session.client('iam')

        summary = iam.get_account_summary().get('SummaryMap', {})

        # AccountMFAEnabled = 1 jika root user punya MFA aktif
        root_mfa_enabled = bool(summary.get('AccountMFAEnabled', 0))

        # Cek password policy (best practice security)
        try:
            policy = iam.get_account_password_policy().get('PasswordPolicy', {})
            password_policy_set = True
        except iam.exceptions.NoSuchEntityException:
            policy = {}
            password_policy_set = False
        except Exception:
            policy = {}
            password_policy_set = False

        assessment_data['services']['iam'] = {
            'count': summary.get('Users', 0),
            'users_count':              summary.get('Users', 0),
            'groups_count':             summary.get('Groups', 0),
            'roles_count':              summary.get('Roles', 0),
            'policies_count':           summary.get('Policies', 0),
            'mfa_devices_in_use':       summary.get('MFADevicesInUse', 0),
            'account_access_keys':      summary.get('AccountAccessKeysPresent', 0),
            'root_mfa_enabled':         root_mfa_enabled,
            'password_policy_set':      password_policy_set,
            'min_password_length':      policy.get('MinimumPasswordLength', 0),
            'require_symbols':          policy.get('RequireSymbols', False),
            'require_numbers':          policy.get('RequireNumbers', False),
            'require_uppercase':        policy.get('RequireUppercaseCharacters', False),
            'require_lowercase':        policy.get('RequireLowercaseCharacters', False),
            'password_reuse_prevention': policy.get('PasswordReusePrevention', 0),
            'max_password_age':         policy.get('MaxPasswordAge', 0),
        }

        print(f"✓ IAM summary: {summary.get('Users', 0)} users, "
              f"{summary.get('Groups', 0)} groups, "
              f"{summary.get('Roles', 0)} roles")
        print(f"  Root MFA: {'✓ Enabled' if root_mfa_enabled else '✗ DISABLED (risk!)'}")
        print(f"  Password policy: {'✓ Set' if password_policy_set else '✗ Not set'}")
        return True
    except Exception as e:
        print(f"✗ Error inventorying IAM: {str(e)}")
        return False
