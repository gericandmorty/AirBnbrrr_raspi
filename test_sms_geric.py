import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests
from services.traccar_setup_api import get_traccar_setup

# Only send to Geric for this simulation
GERIC_NUMBER = "09510412754"

cfg = get_traccar_setup()
sms_url = cfg["sms_url"]
api_key  = cfg["api_key"]

message = "Test message from AirBnBrrr system. No links included."

headers = {}
if api_key:
    headers["Authorization"] = api_key

payload = {"to": GERIC_NUMBER, "message": message}

print(f"Sending SMS to {GERIC_NUMBER}...")
print(f"URL: {sms_url}")
print(f"Message preview:\n{message[:200]}...")
print()

resp = requests.post(sms_url, json=payload, headers=headers, timeout=15)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text}")

if 200 <= resp.status_code < 300:
    print("\n[OK] SMS sent successfully to Geric!")
else:
    print("\n[FAIL] SMS failed. Check the status code above.")
