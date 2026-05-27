import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests
from services.traccar_setup_api import get_traccar_setup

# Only send to Geric for this simulation
GERIC_NUMBER = "09157513981"

cfg = get_traccar_setup()
sms_url = cfg["sms_url"]
api_key  = cfg["api_key"]

message = (
    "[RULE ENGINE] !! AC Diagnostic Alert !!\n"
    "\n"
    "[HIGH] Power Usage -- TOO HIGH\n"
    "Reading: 651.2 W  |  Safe range: 545-600 W\n"
    "Action: Clean the condenser coil and inspect the run capacitor.\n"
    "\n"
    "[HIGH] Compressor Heat -- TOO HIGH\n"
    "Reading: 96.3 C  |  Safe range: 55-90 C\n"
    "Action: Clean condenser fins and check refrigerant pressure.\n"
    "\n"
    "[HIGH] Cooling Pipe Temperature -- TOO LOW\n"
    "Reading: 2.1 C  |  Safe range: 5-20 C\n"
    "Action: Turn off AC immediately and clean the air filter.\n"
    "\n"
    "View full report: http://airbnbrrr.local:8000/pages/alert?id=44"
)

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
