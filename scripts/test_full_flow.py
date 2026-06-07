"""Test full flow run_cost_optimization dengan pricing terpisah."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import boto3
import os
from dotenv import load_dotenv
from collectors.cost_optimization import run_cost_optimization
from utils.pricing import get_cache_info

load_dotenv()

session = boto3.Session(
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    region_name='ap-southeast-3',
)

# Simulasi data dengan 1 EBS unattached
data = {
    'region': 'ap-southeast-3',
    'services': {
        'ebs': {
            'volumes': [
                {'id': 'vol-test123', 'state': 'available', 'size': 100, 'type': 'gp3', 'encrypted': True},
                {'id': 'vol-test456', 'state': 'available', 'size': 50, 'type': 'gp2', 'encrypted': False},
            ]
        }
    },
    'cost_optimization': {},
}

run_cost_optimization(session, data)

co = data['cost_optimization']
print(f"\n─── Result ───")
print(f"  source:  {co['price_source']}")
print(f"  savings: ${co['total_potential_savings']}/bulan")
print(f"  note:    {co['price_region_note']}")
for f in co['findings']:
    print(f"  → {f['resource_id']}: ${f['estimated_monthly_cost']}/mo ({f['details']})")

# Cek cache info
print(f"\n─── Cache Info ───")
info = get_cache_info('ap-southeast-3')
print(f"  {info}")
