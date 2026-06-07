def inventory_vpc(session, assessment_data):
    """Inventory VPCs"""
    print("\n🌐 Inventarisasi VPCs...")
    try:
        ec2 = session.client('ec2')

        paginator = ec2.get_paginator('describe_vpcs')
        vpc_list = []

        for page in paginator.paginate():
            for vpc in page.get('Vpcs', []):
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

        assessment_data['services']['vpc'] = {
            'count': len(vpc_list),
            'vpcs': vpc_list
        }

        print(f"✓ Found {len(vpc_list)} VPCs")
        return True
    except Exception as e:
        print(f"✗ Error inventorying VPC: {str(e)}")
        return False

def inventory_nat_gateway(session, assessment_data):
    """Inventory NAT Gateways"""
    print("\n🚪 Inventarisasi NAT Gateways...")
    try:
        ec2 = session.client('ec2')

        paginator = ec2.get_paginator('describe_nat_gateways')
        nat_list = []

        for page in paginator.paginate():
            for nat in page.get('NatGateways', []):
                nat_list.append({
                    'id': nat['NatGatewayId'],
                    'vpc_id': nat['VpcId'],
                    'subnet_id': nat['SubnetId'],
                    'state': nat['State'],
                    'connectivity_type': nat.get('ConnectivityType', 'public')
                })

        assessment_data['services']['nat_gateway'] = {
            'count': len(nat_list),
            'nat_gateways': nat_list
        }

        print(f"✓ Found {len(nat_list)} NAT Gateways")
        return True
    except Exception as e:
        print(f"✗ Error inventorying NAT Gateway: {str(e)}")
        return False

def inventory_cloudfront(session, assessment_data):
    """Inventory CloudFront distributions"""
    print("\n🌐 Inventarisasi CloudFront distributions...")
    try:
        cloudfront = session.client('cloudfront')

        paginator = cloudfront.get_paginator('list_distributions')
        dist_list = []

        for page in paginator.paginate():
            distribution_list = page.get('DistributionList', {}) or {}
            for dist in distribution_list.get('Items', []) or []:
                dist_list.append({
                    'id': dist['Id'],
                    'domain': dist['DomainName'],
                    'status': dist['Status'],
                    'enabled': dist['Enabled']
                })

        assessment_data['services']['cloudfront'] = {
            'count': len(dist_list),
            'distributions': dist_list
        }

        print(f"✓ Found {len(dist_list)} CloudFront distributions")
        return True
    except Exception as e:
        print(f"✗ Error inventorying CloudFront: {str(e)}")
        return False

def inventory_route53(session, assessment_data):
    """Inventory Route 53 hosted zones"""
    print("\n🌍 Inventarisasi Route 53 hosted zones...")
    try:
        route53 = session.client('route53')

        paginator = route53.get_paginator('list_hosted_zones')
        zone_list = []

        for page in paginator.paginate():
            for zone in page.get('HostedZones', []):
                zone_list.append({
                    'id': zone['Id'].split('/')[-1],
                    'name': zone['Name'],
                    'type': 'Private' if zone.get('Config', {}).get('PrivateZone', False) else 'Public',
                    'record_count': zone.get('ResourceRecordSetCount', 0),
                    'comment': zone.get('Config', {}).get('Comment', 'N/A')
                })

        assessment_data['services']['route53'] = {
            'count': len(zone_list),
            'hosted_zones': zone_list
        }

        print(f"✓ Found {len(zone_list)} Route 53 hosted zones")
        return True
    except Exception as e:
        print(f"✗ Error inventorying Route 53: {str(e)}")
        return False

def inventory_nlb(session, assessment_data):
    """Inventory Network Load Balancers (NLB)"""
    print("\n⚖️  Inventarisasi Network Load Balancers...")
    try:
        elbv2 = session.client('elbv2')

        paginator = elbv2.get_paginator('describe_load_balancers')
        nlb_list = []

        for page in paginator.paginate():
            for lb in page.get('LoadBalancers', []):
                if lb['Type'] == 'network':
                    listener_count = 0
                    try:
                        listeners_resp = elbv2.describe_listeners(
                            LoadBalancerArn=lb['LoadBalancerArn']
                        )
                        listener_count = len(listeners_resp.get('Listeners', []))
                    except Exception as e:
                        print(f"  ⚠ Error getting listeners for {lb['LoadBalancerName']}: {str(e)}")

                    nlb_list.append({
                        'name': lb['LoadBalancerName'],
                        'arn': lb['LoadBalancerArn'],
                        'dns': lb['DNSName'],
                        'scheme': lb['Scheme'],
                        'state': lb['State']['Code'],
                        'vpc_id': lb['VpcId'],
                        'availability_zones': [az['ZoneName'] for az in lb['AvailabilityZones']],
                        'listener_count': listener_count,
                    })

        assessment_data['services']['nlb'] = {
            'count': len(nlb_list),
            'load_balancers': nlb_list
        }

        print(f"✓ Found {len(nlb_list)} Network Load Balancers")
        return True
    except Exception as e:
        print(f"✗ Error inventorying NLB: {str(e)}")
        return False
