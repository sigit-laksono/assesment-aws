def inventory_ec2(session, assessment_data):
    """Inventory EC2 instances"""
    print("\n🖥️  Inventarisasi EC2 instances...")
    try:
        ec2 = session.client('ec2')

        paginator = ec2.get_paginator('describe_instances')
        instance_list = []

        for page in paginator.paginate():
            for reservation in page.get('Reservations', []):
                for instance in reservation.get('Instances', []):
                    # Extract tags
                    tags = {t['Key']: t['Value'] for t in instance.get('Tags', [])}

                    instance_list.append({
                        # Existing fields
                        'id': instance['InstanceId'],
                        'type': instance['InstanceType'],
                        'state': instance['State']['Name'],
                        'launch_time': instance['LaunchTime'].strftime('%Y-%m-%d %H:%M:%S'),
                        # Platform & Architecture
                        'platform': instance.get('Platform', 'Linux'),
                        'architecture': instance.get('Architecture', ''),
                        # Network Topology
                        'availability_zone': instance['Placement']['AvailabilityZone'],
                        'vpc_id': instance.get('VpcId', ''),
                        'subnet_id': instance.get('SubnetId', ''),
                        'public_ip': instance.get('PublicIpAddress', None),
                        # EBS Optimized
                        'ebs_optimized': instance.get('EbsOptimized', False),
                        # Tags
                        'name': tags.get('Name', ''),
                        'environment': tags.get('Environment', '') or tags.get('Env', ''),
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

        paginator = lambda_client.get_paginator('list_functions')
        function_list = []

        for page in paginator.paginate():
            for func in page.get('Functions', []):
                function_list.append({
                    'name': func['FunctionName'],
                    'runtime': func.get('Runtime', 'N/A'),
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

        paginator = eks.get_paginator('list_clusters')
        cluster_names = []
        for page in paginator.paginate():
            cluster_names.extend(page.get('clusters', []))

        cluster_list = []
        for cluster_name in cluster_names:
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

def inventory_ecr(session, assessment_data):
    """Inventory ECR repositories"""
    print("\n📦 Inventarisasi ECR repositories...")
    try:
        ecr = session.client('ecr')

        repo_paginator = ecr.get_paginator('describe_repositories')
        repo_list = []

        for page in repo_paginator.paginate():
            for repo in page.get('repositories', []):
                # Get image count (also paginated)
                image_count = 0
                try:
                    image_paginator = ecr.get_paginator('list_images')
                    for img_page in image_paginator.paginate(repositoryName=repo['repositoryName']):
                        image_count += len(img_page.get('imageIds', []))
                except Exception:
                    pass

                repo_list.append({
                    'name': repo['repositoryName'],
                    'uri': repo['repositoryUri'],
                    'created_at': repo['createdAt'].strftime('%Y-%m-%d %H:%M:%S'),
                    'image_tag_mutability': repo.get('imageTagMutability', 'N/A'),
                    'scan_on_push': repo.get('imageScanningConfiguration', {}).get('scanOnPush', False),
                    'image_count': image_count
                })

        assessment_data['services']['ecr'] = {
            'count': len(repo_list),
            'repositories': repo_list
        }

        print(f"✓ Found {len(repo_list)} ECR repositories")
        return True
    except Exception as e:
        print(f"✗ Error inventorying ECR: {str(e)}")
        return False

def inventory_alb(session, assessment_data):
    """Inventory Application Load Balancers (ALB)"""
    print("\n⚖️  Inventarisasi Application Load Balancers...")
    try:
        elbv2 = session.client('elbv2')

        paginator = elbv2.get_paginator('describe_load_balancers')
        alb_list = []

        for page in paginator.paginate():
            for lb in page.get('LoadBalancers', []):
                # Filter hanya ALB (Application Load Balancer)
                if lb['Type'] == 'application':
                    # Get listener count
                    listener_count = 0
                    try:
                        listeners_resp = elbv2.describe_listeners(
                            LoadBalancerArn=lb['LoadBalancerArn']
                        )
                        listener_count = len(listeners_resp.get('Listeners', []))
                    except Exception as e:
                        print(f"  ⚠ Error getting listeners for {lb['LoadBalancerName']}: {str(e)}")

                    alb_list.append({
                        'name': lb['LoadBalancerName'],
                        'arn': lb['LoadBalancerArn'],
                        'dns': lb['DNSName'],
                        'scheme': lb['Scheme'],
                        'state': lb['State']['Code'],
                        'vpc_id': lb['VpcId'],
                        'availability_zones': [az['ZoneName'] for az in lb['AvailabilityZones']],
                        'listener_count': listener_count,
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
