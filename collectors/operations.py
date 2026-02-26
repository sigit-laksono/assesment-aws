def inventory_cloudtrail(session, assessment_data):
    """Inventory CloudTrail trails"""
    print("\n🔍 Inventarisasi CloudTrail trails...")
    try:
        cloudtrail = session.client('cloudtrail')
        
        trails = cloudtrail.describe_trails()
        trail_list = []
        
        for trail in trails.get('trailList', []):
            # Get trail status
            try:
                status = cloudtrail.get_trail_status(Name=trail['TrailARN'])
                is_logging = status.get('IsLogging', False)
            except:
                is_logging = False
            
            trail_list.append({
                'name': trail['Name'],
                'arn': trail['TrailARN'],
                'is_logging': is_logging,
                'is_multi_region': trail.get('IsMultiRegionTrail', False),
                's3_bucket': trail.get('S3BucketName', 'N/A')
            })
        
        assessment_data['services']['cloudtrail'] = {
            'count': len(trail_list),
            'trails': trail_list
        }
        
        print(f"✓ Found {len(trail_list)} CloudTrail trails")
        return True
    except Exception as e:
        print(f"✗ Error inventorying CloudTrail: {str(e)}")
        return False

def inventory_config(session, assessment_data):
    """Inventory AWS Config recorders"""
    print("\n⚙️  Inventarisasi AWS Config recorders...")
    try:
        config = session.client('config')
        
        recorders = config.describe_configuration_recorders()
        recorder_list = []
        
        for recorder in recorders.get('ConfigurationRecorders', []):
            # Get recorder status
            try:
                status_response = config.describe_configuration_recorder_status(
                    ConfigurationRecorderNames=[recorder['name']]
                )
                status = status_response['ConfigurationRecordersStatus'][0]
                is_recording = status.get('recording', False)
            except:
                is_recording = False
            
            recorder_list.append({
                'name': recorder['name'],
                'role_arn': recorder.get('roleARN', 'N/A'),
                'is_recording': is_recording,
                'record_all': recorder.get('recordingGroup', {}).get('allSupported', False)
            })
        
        assessment_data['services']['config'] = {
            'count': len(recorder_list),
            'recorders': recorder_list
        }
        
        print(f"✓ Found {len(recorder_list)} AWS Config recorders")
        return True
    except Exception as e:
        print(f"✗ Error inventorying AWS Config: {str(e)}")
        return False
