#!/usr/bin/env python3
from datetime import datetime
import sys
import json
from pathlib import Path

# Add the parent directory to python path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

try:
    from database import get_db_connection
    from services.rule_engine import analyze_with_rules
except ImportError as e:
    print(f"Error importing modules: {e}")
    sys.exit(1)

# Simulating an extremely unhealthy water-cooled AC / Chiller operating day
MOCK_TELEMETRY = {
    "compressor_suction_pressure": 0.25,        # < 0.30 MPa -> Low Suction Pressure (High Severity)
    "compressor_discharge_pressure": 2.35,      # > 2.20 MPa -> High Discharge Pressure (High Severity)
    "water_inlet_temp_c": 36.0,                 # > 35.0 °C -> High Water Inlet Temp (High Severity)
    "water_outlet_temp_c": 36.0,                # Outlet == Inlet -> Zero/Negative difference (High Severity)
    "water_inlet_pressure_mpa": 1.5,
    "water_outlet_pressure_mpa": 0.8,
    "fan_amperes": 27.0,
    "compressor_amperes": 52.0,                 # > 45.0 A -> Overloaded Compressor (Critical Severity)
    "ac_inlet_temp_in": 25.0,
    "ac_inlet_temp_out": 26.0,
    "ac_outlet_temp": 25.0                      # Outlet == Inlet -> Poor Cooling (High Severity)
}

def inject_mock_anomaly():
    print("=== STEP 1: RUNNING RULE ENGINE ON SIMULATED CHILLER ANOMALY ===")
    rule_result = analyze_with_rules(MOCK_TELEMETRY)
    
    print(f"Overall Severity : {rule_result['overall_severity']}")
    print(f"Sensors Checked  : {rule_result['sensors_checked']}")
    print(f"Rules Triggered  : {rule_result['sensors_triggered']}")
    print("\n--- DETAILED VERDICTS ---")
    
    for step in rule_result["computation_steps"]:
        verdict = step["result"]
        icon = "🚨" if verdict == "TRIGGERED" else ("✅" if verdict == "PASS" else "ℹ️")
        expr = step.get("expression") or step.get("reason", "")
        sensor = step["sensor"]
        value = step["value"]
        print(f"  {icon} [{verdict:9}] {sensor:<40} | Value: {value:<10} | {expr}")

    print("\n=== STEP 2: GENERATING MOCK AI EXPLANATION ===")
    # Simulate what the LLM Layer 2 would say about these symptoms
    mock_ai_diagnoses = {
        "diagnoses": [
            {
                "issue": "Severe Condenser Cooling Water Flow Failure with Compressor Thermal Overload",
                "status": "Current",
                "confidence_score": 98,
                "root_cause": (
                    "Water inlet temperature is 36.0°C and outlet is 36.0°C (0.0°C difference) "
                    "while compressor draws 52.0A. High head pressure (2.35 MPa) and low suction (0.25 MPa) "
                    "with high current draw confirms the condenser cannot reject heat, overloading the motor."
                ),
                "severity": "Critical",
                "recommended_action": (
                    "Shut down system immediately. Check condenser cooling pump power and water flow valves. "
                    "Clean/descale condenser tubes and check for blockages."
                )
            },
            {
                "issue": "No Cooling Performance (AC Supply Air == Indoor Air)",
                "status": "Current",
                "confidence_score": 95,
                "root_cause": (
                    "AC inlet temperature is 25.0°C and supply outlet temperature is 25.0°C (0.0°C split) "
                    "while compressor is drawing 52.0A. Mechanical cooling is completely absent."
                ),
                "severity": "High",
                "recommended_action": (
                    "Verify compressor suction and discharge valves for internal leaking once condenser flow is restored."
                )
            }
        ]
    }

    # Combined payload format
    combined_payload = json.dumps({
        "rule_diagnoses": rule_result,
        "ai_diagnoses": mock_ai_diagnoses
    })

    # Summary formatting
    findings = rule_result["findings"]
    summary_lines = ["🚨 Simulated Water-Cooled AC/Chiller Fault Alert! 🚨"]
    for f in findings[:2]:
        parts = [p.strip() for p in f["recommended_action"].split(". ") if p.strip()]
        if parts:
            if parts[0].isdigit() and len(parts) > 1:
                action_short = f"{parts[0]}. {parts[1]}."
            else:
                action_short = f"{parts[0]}."
        else:
            action_short = "Inspect unit."
        summary_lines.append(f"\n[{f['severity'].upper()}] {f['issue']}\nAction: {action_short}")
    summary_lines.append("\nCheck full system report for details.")
    summary_text = "\n".join(summary_lines)

    print("\n=== STEP 3: INSERTING ALARM RECORD INTO SUPABASE ===")
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute(
        "INSERT INTO alerts (timestamp, summary, diagnoses) VALUES (%s, %s, %s) RETURNING id, timestamp::text",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), summary_text, combined_payload)
    )
    inserted = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    print(f"✅ Success! Mock Alert inserted.")
    print(f"  - Alert ID   : {inserted['id']}")
    print(f"  - Created At : {inserted['timestamp']}")
    print(f"  - Summary    : {summary_text.splitlines()[0]}")

if __name__ == "__main__":
    inject_mock_anomaly()
