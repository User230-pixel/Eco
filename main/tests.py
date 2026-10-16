from django.test import TestCase
import hmac
import hashlib
import json

def test_webhook_signature():
    secret_key = "your-test-secret-key"
    data = {
        "event": "payment.succeeded",
        "object": {
            "id": "test_payment_id",
            "metadata": {"order_id": 123}
        }
    }
    body = json.dumps(data)
    signature = hmac.new(
        key=secret_key.encode('utf-8'),
        msg=body.encode('utf-8'),
        digestmod=hashlib.sha256
    ).hexdigest()
    