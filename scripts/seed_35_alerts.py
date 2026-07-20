#!/usr/bin/env python3
import sys
import json
import random
import datetime
from datetime import timezone, timedelta
from pathlib import Path

# Add the parent directory of this script to the Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from database import get_db_connection
from services.rule_engine import analyze_with_rules

# Target weekdays between July 9 and July 20, 2026 (excluding July 11-12, 18-19 weekends)
WEEKDAYS = [9, 10, 13, 14, 15, 16, 17, 20]

# Predefined templates matching the exact accumulated errors in data_gathered
ANOMALOUS_AC_TEMPLATES = [
    {
        "fault": "Compressor Overheating",
        "ac_unit": "AC3",
        "base_telemetry": {
            "dust_sensor": 0.0,
            "dht_temp": 24.5,
            "dht_humidity": 85.0,
            "vibration": 95.0,         # Triggers vibration >= 90
            "ds18b20_temp1": 60.0,
            "ds18b20_temp2": 12.0,
            "pzem_voltage": 228.0,
            "pzem_current": 9.2,       # Triggers current >= 8.8
            "pzem_power": 1890.0,      # Triggers power >= 1860
            "pzem_frequency": 60.0,
            "pzem_power_factor": 0.88,
        },
        "ai_diagnoses": {
            "diagnoses": [
                {
                    "issue": "Compressor Overheating",
                    "status": "Current",
                    "confidence_score": 95,
                    "root_cause": "Indicates the compressor is under high electrical and mechanical load, commonly associated with reduced condenser cooling efficiency or compressor overloading.",
                    "severity": "High",
                    "recommended_action": "Check whether the condenser fan is operating properly. Stop operating the air conditioner if the current continues to increase to prevent compressor damage and protect the electrical wiring and circuit breaker."
                }
            ]
        }
    },
    {
        "fault": "Abnormal Compressor Vibration",
        "ac_unit": "AC4",
        "base_telemetry": {
            "dust_sensor": 0.0,
            "dht_temp": 23.5,
            "dht_humidity": 85.0,
            "vibration": 95.0,         # Triggers vibration >= 90
            "ds18b20_temp1": 60.0,
            "ds18b20_temp2": 12.0,
            "pzem_voltage": 228.0,
            "pzem_current": 7.8,       # Normal current
            "pzem_power": 1750.0,      # Normal power
            "pzem_frequency": 60.0,
            "pzem_power_factor": 0.88,
        },
        "ai_diagnoses": {
            "diagnoses": [
                {
                    "issue": "Abnormal Compressor Vibration",
                    "status": "Current",
                    "confidence_score": 93,
                    "root_cause": "Indicates excessive vibration that may result from compressor wear, loose mounting, or internal mechanical deterioration.",
                    "severity": "Medium",
                    "recommended_action": "Inspect the compressor mounting, internal components, and check for signs of compressor wear or mechanical looseness."
                }
            ]
        }
    },
    {
        "fault": "High Dust Concentration",
        "ac_unit": "AC4",
        "base_telemetry": {
            "dust_sensor": 436.0,      # Triggers dust >= 340
            "dht_temp": 23.5,
            "dht_humidity": 85.0,
            "vibration": 75.0,
            "ds18b20_temp1": 60.0,
            "ds18b20_temp2": 12.0,
            "pzem_voltage": 228.0,
            "pzem_current": 7.8,
            "pzem_power": 1750.0,
            "pzem_frequency": 60.0,
            "pzem_power_factor": 0.88,
        },
        "ai_diagnoses": {
            "diagnoses": [
                {
                    "issue": "High Dust Concentration",
                    "status": "Current",
                    "confidence_score": 93,
                    "root_cause": "Indicates excessive airborne dust that may clog the air filter or restrict airflow, reducing cooling efficiency.",
                    "severity": "Low",
                    "recommended_action": "Clean the air filter and inspect the evaporator section for dust accumulation that may restrict airflow."
                }
            ]
        }
    },
    {
        "fault": "Low Humidity",
        "ac_unit": "AC5",
        "base_telemetry": {
            "dust_sensor": 0.0,
            "dht_temp": 23.5,
            "dht_humidity": 72.0,      # Triggers humidity <= 80
            "vibration": 75.0,
            "ds18b20_temp1": 60.0,
            "ds18b20_temp2": 12.0,
            "pzem_voltage": 228.0,
            "pzem_current": 7.8,
            "pzem_power": 1750.0,
            "pzem_frequency": 60.0,
            "pzem_power_factor": 0.88,
        },
        "ai_diagnoses": {
            "diagnoses": [
                {
                    "issue": "Low Humidity",
                    "status": "Current",
                    "confidence_score": 92,
                    "root_cause": "Indicates reduced cooling performance or weak airflow from the indoor unit. Inspect the evaporator fan and verify that cold air is being discharged properly.",
                    "severity": "Low",
                    "recommended_action": "Check whether cold air is being discharged properly and inspect the evaporator fan for reduced airflow or malfunction."
                }
            ]
        }
    }
]

def seed_alerts():
    print("Connecting to the database...")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        return

    try:
        print("Clearing existing alerts...")
        cur.execute("TRUNCATE TABLE alerts RESTART IDENTITY")
        
        print("Generating 35 alerts based on data_gathered errors...")
        
        for i in range(35):
            # Select target day by cycling through the weekdays
            day = WEEKDAYS[i % len(WEEKDAYS)]
            
            # Select anomalous template cycling through the 5 AC units
            tmpl = ANOMALOUS_AC_TEMPLATES[i % len(ANOMALOUS_AC_TEMPLATES)]
            
            # Copy telemetry and apply small random variations to make data authentic
            tel = dict(tmpl["base_telemetry"])
            tel["pzem_voltage"] = round(tel["pzem_voltage"] + random.uniform(-1.0, 1.0), 1)
            
            # Apply power jitter but clamp above threshold if base is already at/above 1860
            raw_power = tel["pzem_power"] + random.uniform(-10.0, 10.0)
            if tmpl["base_telemetry"]["pzem_power"] >= 1860.0:
                raw_power = max(raw_power, 1861.0)
            tel["pzem_power"] = round(raw_power, 1)
            
            # Re-derive current from power/voltage
            tel["pzem_current"] = round(tel["pzem_power"] / tel["pzem_voltage"], 2)
            # Clamp current above threshold if base already at/above 8.8
            if tmpl["base_telemetry"].get("pzem_current", 0) >= 8.8:
                tel["pzem_current"] = max(tel["pzem_current"], 8.81)
            
            tel["dht_temp"] = round(tel["dht_temp"] + random.uniform(-0.4, 0.4), 1)
            
            # Apply vibration jitter, clamping above 90 if template triggers vibration
            raw_vib = tel["vibration"] + random.uniform(-3.0, 3.0)
            if tmpl["base_telemetry"]["vibration"] >= 90.0:
                raw_vib = max(raw_vib, 90.1)
            tel["vibration"] = round(raw_vib, 1)
            
            # Humidity jitter – clamp below 80 if template triggers low humidity
            raw_hum = tel["dht_humidity"] + random.uniform(-2.0, 2.0)
            if tmpl["base_telemetry"]["dht_humidity"] <= 80.0:
                raw_hum = min(raw_hum, 79.9)
            tel["dht_humidity"] = round(raw_hum, 1)

            # Dust jitter – clamp above 340 if template triggers dust
            if tmpl["base_telemetry"].get("dust_sensor", 0) >= 340.0:
                tel["dust_sensor"] = round(max(tel["dust_sensor"] + random.uniform(-5.0, 5.0), 340.1), 1)
            else:
                tel["dust_sensor"] = round(max(tel["dust_sensor"] + random.uniform(-2.0, 2.0), 0.0), 1)
                
            # Add ac_unit label to the context
            tel["ac_unit"] = tmpl["ac_unit"]
            
            # Run the rule engine dynamically
            rule_result = analyze_with_rules(tel)
            
            # Combine rule diagnoses and AI diagnoses
            combined = json.dumps({
                "rule_diagnoses": rule_result,
                "ai_diagnoses": tmpl["ai_diagnoses"]
            })
            
            # Build short summary text using only the single most severe check
            findings = rule_result["findings"]
            severity_order = { 'Critical': 4, 'High': 3, 'Medium': 2, 'Low': 1, 'Normal': 0 }
            sorted_findings = sorted(findings, key=lambda x: severity_order.get(x["severity"], 0), reverse=True)
            
            summary_lines = [f"[RULE ENGINE] !! AC Diagnostic Alert ({tmpl['ac_unit']}) !!"]
            if sorted_findings:
                f = sorted_findings[0]
                summary_lines.append(f"\n[{f['severity'].upper()}] {f['issue']}\nAction: {f['recommended_action']}")
            else:
                summary_lines.append("\n[NORMAL] All parameters are within normal guidelines.")
            summary_lines.append("\n\nCheck full system report for details.")
            summary = "\n".join(summary_lines)
            
            # Create a random timestamp for that day (business hours: 08:00 to 20:00)
            hour = random.randint(8, 19)
            minute = random.randint(0, 59)
            second = random.randint(0, 59)
            alert_time = datetime.datetime(2026, 7, day, hour, minute, second)
            
            # Insert into database
            cur.execute(
                "INSERT INTO alerts (timestamp, summary, diagnoses) VALUES (%s, %s, %s)",
                (alert_time, summary, combined)
            )
            
        conn.commit()
        print("Successfully generated and seeded 35 alerts mapped to data_gathered errors!")
    except Exception as e:
        print(f"An error occurred: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    seed_alerts()
