from datetime import datetime, timedelta

def get_billing_data(session, assessment_data):
    """Ambil data billing satu bulan terakhir dari Cost Explorer"""
    print(f"\n📊 Mengambil data billing bulan lalu...")
    
    try:
        ce = session.client('ce', region_name='us-east-1')  # Cost Explorer hanya di us-east-1
        
        # Calculate date range - bulan lalu saja
        end_date = datetime.now().date().replace(day=1)  # Awal bulan ini
        start_date = (end_date - timedelta(days=1)).replace(day=1)  # Awal bulan lalu
        
        print(f"  Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        
        # Get total cost first (without grouping) - try multiple metrics
        response_total = ce.get_cost_and_usage(
            TimePeriod={
                'Start': start_date.strftime('%Y-%m-%d'),
                'End': end_date.strftime('%Y-%m-%d')
            },
            Granularity='MONTHLY',
            Metrics=['UnblendedCost', 'BlendedCost']
        )
        
        # Get cost by service
        response = ce.get_cost_and_usage(
            TimePeriod={
                'Start': start_date.strftime('%Y-%m-%d'),
                'End': end_date.strftime('%Y-%m-%d')
            },
            Granularity='MONTHLY',
            Metrics=['UnblendedCost'],
            GroupBy=[
                {'Type': 'DIMENSION', 'Key': 'SERVICE'}
            ]
        )
        
        # Process billing data
        monthly_costs = []
        service_costs = {}
        
        # Get total from ungrouped response - try UnblendedCost first
        total_cost_actual = 0
        total_cost_blended = 0
        if response_total['ResultsByTime']:
            result = response_total['ResultsByTime'][0]
            total_cost_actual = float(result['Total']['UnblendedCost']['Amount'])
            total_cost_blended = float(result['Total']['BlendedCost']['Amount'])
        
        for result in response['ResultsByTime']:
            period = result['TimePeriod']['Start']
            total_cost = 0
            
            for group in result['Groups']:
                service = group['Keys'][0]
                cost = float(group['Metrics']['UnblendedCost']['Amount'])
                
                if cost > 0:
                    if service not in service_costs:
                        service_costs[service] = []
                    service_costs[service].append({
                        'period': period,
                        'cost': cost
                    })
                    total_cost += cost
            
            monthly_costs.append({
                'period': period,
                'total': total_cost_actual if total_cost_actual > 0 else total_cost  # Use actual total
            })
        
        assessment_data['billing_data'] = {
            'monthly_costs': monthly_costs,
            'service_costs': service_costs,
            'period': f"Bulan Lalu: {start_date.strftime('%B %Y')}",
            'total_actual': total_cost_actual,
            'total_blended': total_cost_blended
        }
        
        # Get top services
        total_by_service = {}
        for service, costs in service_costs.items():
            total_by_service[service] = sum(c['cost'] for c in costs)
        
        top_services = sorted(total_by_service.items(), key=lambda x: x[1], reverse=True)[:10]
        assessment_data['billing_data']['top_services'] = top_services
        
        print(f"✓ Data billing berhasil diambil")
        print(f"✓ Period: {start_date.strftime('%B %Y')}")
        print(f"✓ Total Actual Cost: ${total_cost_actual:.2f}")
        print(f"✓ Total services dengan biaya: {len(service_costs)}")
        print(f"✓ Top 3 services:")
        for service, cost in top_services[:3]:
            print(f"  - {service}: ${cost:.2f}")
        
        return True
        
    except Exception as e:
        print(f"✗ Error getting billing data: {str(e)}")
        print(f"  Note: Pastikan Cost Explorer API sudah diaktifkan di account AWS")
        return False
