def inventory_sns(session, assessment_data):
    """Inventory SNS topics"""
    print("\n📢 Inventarisasi SNS topics...")
    try:
        sns = session.client('sns')
        
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
        
        assessment_data['services']['sns'] = {
            'count': len(topic_list),
            'topics': topic_list
        }
        
        print(f"✓ Found {len(topic_list)} SNS topics")
        return True
    except Exception as e:
        print(f"✗ Error inventorying SNS: {str(e)}")
        return False

def inventory_msk(session, assessment_data):
    """Inventory MSK (Managed Streaming for Apache Kafka) clusters"""
    print("\n📊 Inventarisasi MSK clusters...")
    try:
        kafka = session.client('kafka')
        
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
        
        assessment_data['services']['msk'] = {
            'count': len(cluster_list),
            'clusters': cluster_list
        }
        
        print(f"✓ Found {len(cluster_list)} MSK clusters")
        return True
    except Exception as e:
        print(f"✗ Error inventorying MSK: {str(e)}")
        return False

def inventory_amazonmq(session, assessment_data):
    """Inventory Amazon MQ brokers"""
    print("\n🔄 Inventarisasi Amazon MQ brokers...")
    try:
        mq = session.client('mq')
        
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
        
        assessment_data['services']['amazonmq'] = {
            'count': len(broker_list),
            'brokers': broker_list
        }
        
        print(f"✓ Found {len(broker_list)} Amazon MQ brokers")
        return True
    except Exception as e:
        print(f"✗ Error inventorying Amazon MQ: {str(e)}")
        return False

def inventory_glue(session, assessment_data):
    """Inventory AWS Glue databases and jobs"""
    print("\n🔧 Inventarisasi AWS Glue...")
    try:
        glue = session.client('glue')
        
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
        
        assessment_data['services']['glue'] = {
            'count': len(db_list) + len(job_list),
            'databases': db_list,
            'jobs': job_list
        }
        
        print(f"✓ Found {len(db_list)} Glue databases and {len(job_list)} Glue jobs")
        return True
    except Exception as e:
        print(f"✗ Error inventorying AWS Glue: {str(e)}")
        return False

def inventory_cloudwatch(session, assessment_data):
    """Inventory CloudWatch alarms"""
    print("\n📊 Inventarisasi CloudWatch alarms...")
    try:
        cloudwatch = session.client('cloudwatch')
        
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
        
        assessment_data['services']['cloudwatch'] = {
            'count': len(alarm_list),
            'alarms': alarm_list
        }
        
        print(f"✓ Found {len(alarm_list)} CloudWatch alarms")
        return True
    except Exception as e:
        print(f"✗ Error inventorying CloudWatch: {str(e)}")
        return False
