import json
from decimal import Decimal

class DecimalEncoder(json.JSONEncoder):
    """Helper untuk encode Decimal ke JSON"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)
