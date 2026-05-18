import json
from services.ai_predictor import ask
from services.traccar_sms import send_sms
from services.alerts_api import create_alert, AlertIn

def format_for_sms(api_response_string):
    """
    Parses the JSON AI response and formats it for an SMS message.
    Limits output to High/Medium severity to save characters.
    """
    try:
        # Parse the JSON string into a Python dictionary
        data = json.loads(api_response_string)
        diagnoses = data.get("diagnoses", [])
    except json.JSONDecodeError:
        return "⚠️ Alert: Diagnostics completed, but data formatting failed."

    # Filter for High and Medium severity issues
    urgent_issues = [d for d in diagnoses if d.get("severity") in ["High", "Medium"]]

    # If everything is Low severity/Normal
    if not urgent_issues:
        return "✅ AC Status: Normal. No urgent issues detected."

    # Build the SMS string
    sms_message = "🚨 AC Diagnostic Alert 🚨\n"
    
    # Limit to the top 2 issues to prevent the SMS from getting too long
    for issue in urgent_issues[:2]:
        title = issue.get("issue", "Unknown")
        severity = issue.get("severity", "Unknown").upper()
        
        # Take just the first sentence of the recommended action to save space
        action_full = issue.get("recommended_action", "Inspect unit.")
        action_short = action_full.split(". ")[0] + "." 
        
        sms_message += f"\n[{severity}] {title}\nAction: {action_short}\n"

    sms_message += "\nCheck full system report for details."
    
    return sms_message

def ac_status_to_str(status):
    if status == 0:
        return "Off"
    elif status == 1:
        return "Fan"
    elif status == 2:
        return "Low Cool"
    elif status == 3:
        return "Medium Cool"
    elif status == 4:
        return "High Cool"
    else:
        return "Unknown"

# ==========================================
# 1. THE COMBINED PROMPT TEMPLATE
# Combines the AI's persona, knowledge base, formatting rules,
# and the specific telemetry data into a single string.
# ==========================================
def generate_combined_prompt(telemetry_data):
    # Note: Double curly braces {{ }} are used below to escape 
    # the JSON brackets so the Python f-string doesn't break.
    return f"""You are an expert HVAC diagnostic AI. Your task is to analyze IoT sensor telemetry from a Window Type Air Conditioner and perform Proactive Fault Detection. You are not limited to identifying a single issue; you should detect multiple possible failures currently affecting the AC, as well as predict possible future failures based on the telemetry trends.

SYSTEM SPECIFICATIONS:
- Capacity: 0.6 HP (5,697 kJ/h or 5,400 BTU/h)
- Type: Manual Window Type (Non-Inverter)
- Refrigerant: R410A
- Expected Power Consumption: 545W - 600W
- Voltage/Frequency: 220-230V / 60Hz / 1Ph

SENSOR CONTEXT & PLACEMENT:
- Dust Sensor: Located behind the front filter. High values indicate a dirty filter restricting airflow.
- Return Air (AC Output Temp/Humidity): Measures ambient air entering the unit.
- Compressor Vibration: Mounted on the compressor. High vibration indicates loose mounts, mechanical wear, or hard starting.
- Discharge Line Temp: Leaving the compressor. Abnormally high temps suggest a dirty condenser coil or low refrigerant.
- Suction Line Temp: Leaving the indoor coil. Freezing/very low temps suggest restricted airflow (dirty filter/evaporator) or a stuck contactor.
- Power Monitor: Main input. Power > 600W suggests an overworked compressor or capacitor failing. Power < 545W (but > 0) suggests the fan is running but the compressor failed to start.

INSTRUCTIONS:
Analyze the provided telemetry data. Provide a structured response detailing all current and potential future issues.
Format your response as a JSON object containing a "diagnoses" array. Each object in the array must have the following keys:
{{
  "diagnoses": [
    {{
      "issue": "Clear explanation of the suspected or predicted issue",
      "status": "Current or Predicted",
      "confidence_score": "Percentage (0-100%) indicating how certain the AI is about this diagnosis",
      "root_cause": "The specific sensor readings that lead to this conclusion",
      "severity": "Low, Medium, High, or Critical",
      "recommended_action": "Actionable steps for the user or technician"
    }}
  ]
}}

--------------------------------------------------

An anomaly trigger has been activated. Please analyze the following real-time sensor telemetry:

{json.dumps(telemetry_data, indent=4)}

Based on the AC specifications and the sensor context provided, what are the current and potential future issues?
"""

# ==========================================
# 2. YOUR REFACTORED FUNCTION
# ==========================================
def process_anomaly(anomaly_data):
    """
    Process the detected anomaly, format the keys for readability, 
    and prepare the single combined prompt for the AI API.
    """
    print("Processing raw anomaly data...")

    # Map raw keys to human-readable keys for better AI understanding
    clean_data = {
        "Dust Level": anomaly_data.pop("dust_sensor", None),
        "Return Air Temperature (C)": anomaly_data.pop("dht_temp", None),
        "Return Air Humidity (%)": anomaly_data.pop("dht_humidity", None),
        "Compressor Vibration (g)": anomaly_data.pop("vibration", None),
        "Compressor Discharge Line Temp (C)": anomaly_data.pop("ds18b20_temp1", None),
        "Compressor Suction Line Temp (C)": anomaly_data.pop("ds18b20_temp2", None),
        "Voltage (V)": anomaly_data.pop("pzem_voltage", None),
        "Current (A)": anomaly_data.pop("pzem_current", None),
        "Power (W)": anomaly_data.pop("pzem_power", None),
        "Energy (kWh)": anomaly_data.pop("pzem_energy", None),  
        "Frequency (Hz)": anomaly_data.pop("pzem_frequency", None),
        "Power Factor": anomaly_data.pop("pzem_power_factor", None),
        "AC Status": ac_status_to_str(anomaly_data.pop("ac_status", None)),
        "AC Thermostat": anomaly_data.pop("ac_thermostat", None)
    }
    
    # Remove any keys that weren't present in the original payload to keep the prompt clean
    clean_data = {k: v for k, v in clean_data.items() if v is not None}

    # Generate the single combined prompt text
    combined_prompt_text = generate_combined_prompt(clean_data)
    
    print("\n--- PROMPT READY FOR API ---")
    print(combined_prompt_text)
    print("----------------------------\n")
    
    try:
        api_response = ask(combined_prompt_text)
    except Exception as e:
        err_text = str(e)
        fail_sms_message = (
            "AI prediction failed. Possible API limit reached. "
            "Please switch to another API in AI Setup. "
            f"Error: {err_text[:200]}"
        )

        print("\n--- AI PREDICTION ERROR ---")
        print(fail_sms_message)
        print("---------------------------\n")

        alert = create_alert(
            AlertIn(
                summary=fail_sms_message,
                diagnoses=json.dumps({"error": err_text})
            )
        )

        fail_sms_message += "\n\nhttp://airbnbrrr.local:8000/alerts/" + str(alert.id)
        send_sms(fail_sms_message)
        return

    print("\n--- AI RESPONSE ---")
    print(api_response)
    print("-------------------\n")
    
    
    # Prepare SMS using original API response string when available
    sms_source = api_response if isinstance(api_response, str) else json.dumps(response_data)
    sms_message = format_for_sms(sms_source)
    print("\n--- FORMATTED SMS ---")
    print(sms_message)
    print("---------------------\n")

    alert_in = AlertIn(
        summary=sms_message,
        diagnoses=api_response if isinstance(api_response, str) else json.dumps(api_response)
    )
    
    alert = create_alert(alert_in)
    
    sms_message += "\n\nhttp://airbnbrrr.local:8000/alerts/" + str(alert.id)
    send_sms(sms_message)