def inventory_rds(session, assessment_data):
    """Inventory RDS instances"""
    print("\n🗄️  Inventarisasi RDS instances...")
    try:
        rds = session.client('rds')
        
        instances = rds.describe_db_instances()
        instance_list = []
        
        for instance in instances['DBInstances']:
            instance_list.append({
                'id': instance['DBInstanceIdentifier'],
                'engine': instance['Engine'],
                'class': instance['DBInstanceClass'],
                'status': instance['DBInstanceStatus']
            })
        
        assessment_data['services']['rds'] = {
            'count': len(instance_list),
            'instances': instance_list
        }
        
        print(f"✓ Found {len(instance_list)} RDS instances")
        return True
    except Exception as e:
        print(f"✗ Error inventorying RDS: {str(e)}")
        return False

def inventory_dynamodb(session, assessment_data):
    """Inventory DynamoDB tables"""
    print("\n🗃️  Inventarisasi DynamoDB tables...")
    try:
        dynamodb = session.client('dynamodb')
        
        tables = dynamodb.list_tables()
        table_list = []
        
        for table_name in tables.get('TableNames', []):
            try:
                table_info = dynamodb.describe_table(TableName=table_name)
                table = table_info['Table']
                table_list.append({
                    'name': table['TableName'],
                    'status': table['TableStatus'],
                    'item_count': table.get('ItemCount', 0),
                    'size_bytes': table.get('TableSizeBytes', 0)
                })
            except Exception as e:
                print(f"  ⚠ Error describing table {table_name}: {str(e)}")
        
        assessment_data['services']['dynamodb'] = {
            'count': len(table_list),
            'tables': table_list
        }
        
        print(f"✓ Found {len(table_list)} DynamoDB tables")
        return True
    except Exception as e:
        print(f"✗ Error inventorying DynamoDB: {str(e)}")
        return False

def inventory_elasticache(session, assessment_data):
    """Inventory ElastiCache clusters"""
    print("\n🔴 Inventarisasi ElastiCache clusters...")
    try:
        elasticache = session.client('elasticache')
        
        clusters = elasticache.describe_cache_clusters()
        cluster_list = []
        
        for cluster in clusters.get('CacheClusters', []):
            cluster_list.append({
                'id': cluster['CacheClusterId'],
                'engine': cluster['Engine'],
                'engine_version': cluster['EngineVersion'],
                'node_type': cluster['CacheNodeType'],
                'status': cluster['CacheClusterStatus'],
                'num_nodes': cluster['NumCacheNodes']
            })
        
        assessment_data['services']['elasticache'] = {
            'count': len(cluster_list),
            'clusters': cluster_list
        }
        
        print(f"✓ Found {len(cluster_list)} ElastiCache clusters")
        return True
    except Exception as e:
        print(f"✗ Error inventorying ElastiCache: {str(e)}")
        return False
