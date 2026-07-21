import json
import re
from decimal import Decimal

class DecimalEncoder(json.JSONEncoder):
    """Helper untuk encode Decimal ke JSON"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)


def slugify(name: str) -> str:
    """Ubah nama customer jadi potongan filename yang aman (mis. 'PT Contoh' -> 'pt_contoh')."""
    slug = re.sub(r'[^a-zA-Z0-9]+', '_', name or '').strip('_').lower()
    return slug or 'customer'
