import boto3
import os
import json
from datetime import datetime
from dotenv import load_dotenv
from utils.helpers import DecimalEncoder

class AssessmentEngine:
    def __init__(
        self,
        customer_name: str | None = None,
        region: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
    ):
        """
        Initialize AWS Assessment.

        Nilai bisa datang dari 2 sumber (prioritas atas ke bawah):
          1. Parameter eksplisit (dari interactive setup)
          2. Environment variable / .env file (mode lama)
        """
        load_dotenv()

        self.access_key    = access_key    or os.getenv('AWS_ACCESS_KEY_ID')
        self.secret_key    = secret_key    or os.getenv('AWS_SECRET_ACCESS_KEY')
        self.region        = region        or os.getenv('AWS_REGION', 'ap-southeast-1')
        self.customer_name = customer_name or os.getenv('CUSTOMER_NAME', 'AWS Customer')
        self.account_id    = os.getenv('AWS_ACCOUNT_ID')   # akan di-overwrite oleh STS

        # Validate credentials existence
        if not self.access_key or not self.secret_key:
            raise ValueError(
                "AWS credentials tidak ditemukan.\n"
                "Jalankan tool secara interaktif atau isi .env file."
            )

        # Initialize boto3 session
        self.session = boto3.Session(
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region,
        )

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
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"output/assessment_data_{timestamp}.json"
        
        os.makedirs('output', exist_ok=True)
        
        with open(filename, 'w') as f:
            json.dump(self.assessment_data, f, indent=2, cls=DecimalEncoder)
        
        print(f"\n✓ Assessment data saved to: {filename}")
        return filename
