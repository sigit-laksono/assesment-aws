import boto3
import os
import json
from datetime import datetime
from utils.helpers import DecimalEncoder

class AssessmentEngine:
    def __init__(
        self,
        customer_name: str = 'AWS Customer',
        region: str = 'ap-southeast-1',
    ):
        """
        Initialize AWS Assessment.

        Credentials diambil dari AWS CLI credential chain (environment,
        ~/.aws/credentials, IAM role, dll). Tidak ada penyimpanan key di .env.
        """
        self.region        = region
        self.customer_name = customer_name
        self.account_id    = None  # di-set oleh validate_credentials()

        # ponytail: ambient credential chain — boto3 resolves from env/config/role
        self.session = boto3.Session(region_name=self.region)

        # Data storage
        self.assessment_data = {
            'customer_name':   self.customer_name,
            'account_id':      self.account_id,
            'region':          self.region,
            'assessment_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'billing_data':       {},
            'services':           {},
            'cost_optimization':  {},
        }

        print(f"✓ Customer : {self.customer_name}")
        print(f"✓ Region   : {self.region}")

    def validate_credentials(self):
        """Validasi AWS credentials dan permissions"""
        try:
            sts = self.session.client('sts')
            identity = sts.get_caller_identity()
            
            self.account_id = identity['Account']
            self.assessment_data['account_id'] = self.account_id
            
            print(f"✓ Credentials valid")
            print(f"✓ Account ID: {self.account_id}")
            print(f"✓ User ARN: {identity['Arn']}")
            return True
        except Exception as e:
            print(f"✗ Error validating credentials: {str(e)}")
            return False

    def save_data(self):
        """Save assessment data ke JSON file"""
        import os
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_dir = os.environ.get("AWS_ASSESS_OUTPUT_DIR", "output")
        os.makedirs(output_dir, exist_ok=True)
        filename = f"{output_dir}/assessment_data_{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(self.assessment_data, f, indent=2, cls=DecimalEncoder)
        
        print(f"\n✓ Assessment data saved to: {filename}")
        return filename
