def inventory_vpc(session, assessment_data):
    """Inventory VPCs"""
    print("\n🌐 Inventarisasi VPCs...")
    try:
        ec2 = session.client('ec2')
        
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
        
        assessment_data['services']['cloudfront'] = {
            'count': len(dist_list),
            'distributions': dist_list
        }
        
        print(f"✓ Found {len(dist_list)} CloudFront distributions")
        return True
    except Exception as e:
        print(f"✗ Error inventorying CloudFront: {str(e)}")
        return False

def inventory_elb(session, assessment_data):
    """Inventory Elastic Load Balancers"""
    print("\n⚖️  Inventarisasi Load Balancers...")
    try:
        elbv2 = session.client('elbv2')
        
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
        
        assessment_data['services']['elb'] = {
            'count': len(lb_list),
            'load_balancers': lb_list
        }
        
        print(f"✓ Found {len(lb_list)} Load Balancers")
        return True
    except Exception as e:
        print(f"✗ Error inventorying ELB: {str(e)}")
        return False
