def inventory_ec2(session, assessment_data):
    """Inventory EC2 instances"""
    print("\n🖥️  Inventarisasi EC2 instances...")
    try:
        ec2 = session.client('ec2')
        
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
        
        assessment_data['services']['ec2'] = {
            'count': len(instance_list),
            'instances': instance_list
        }
        
        print(f"✓ Found {len(instance_list)} EC2 instances")
        return True
    except Exception as e:
        print(f"✗ Error inventorying EC2: {str(e)}")
        return False

def inventory_lambda(session, assessment_data):
    """Inventory Lambda functions"""
    print("\n⚡ Inventarisasi Lambda functions...")
    try:
        lambda_client = session.client('lambda')
        
        functions = lambda_client.list_functions()
        function_list = []
        
        for func in functions['Functions']:
            function_list.append({
                'name': func['FunctionName'],
                'runtime': func['Runtime'],
                'memory': func['MemorySize'],
                'last_modified': func['LastModified']
            })
        
        assessment_data['services']['lambda'] = {
            'count': len(function_list),
            'functions': function_list
        }
        
        print(f"✓ Found {len(function_list)} Lambda functions")
        return True
    except Exception as e:
        print(f"✗ Error inventorying Lambda: {str(e)}")
        return False

def inventory_eks(session, assessment_data):
    """Inventory EKS clusters"""
    print("\n☸️  Inventarisasi EKS clusters...")
    try:
        eks = session.client('eks')
        
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
        
        assessment_data['services']['eks'] = {
            'count': len(cluster_list),
            'clusters': cluster_list
        }
        
        print(f"✓ Found {len(cluster_list)} EKS clusters")
        return True
    except Exception as e:
        print(f"✗ Error inventorying EKS: {str(e)}")
        return False

def inventory_alb(session, assessment_data):
    """Inventory Application Load Balancers (ALB)"""
    print("\n⚖️  Inventarisasi Application Load Balancers...")
    try:
        elbv2 = session.client('elbv2')
        
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
        
        assessment_data['services']['alb'] = {
            'count': len(alb_list),
            'load_balancers': alb_list
        }
        
        print(f"✓ Found {len(alb_list)} Application Load Balancers")
        return True
    except Exception as e:
        print(f"✗ Error inventorying ALB: {str(e)}")
        return False
