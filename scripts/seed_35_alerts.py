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
        "fault": "Compressor Overheating Anomaly",
        "ac_unit": "AC3",
        "base_telemetry": {
            "dust_sensor": None,
            "dht_temp": 22.5,
            "dht_humidity": 98.0,
            "vibration": 72.9,
            "ds18b20_temp1": 97.0,     # Overheating discharge (> 70 °C)
            "ds18b20_temp2": 12.6,
            "pzem_voltage": 228.0,
            "pzem_current": 7.55,
            "pzem_power": 1692.0,
            "pzem_energy": 4.12,
            "pzem_frequency": 60.0,
            "pzem_power_factor": 0.88,
        },
        "ai_diagnoses": {
            "diagnoses": [
                {
                    "issue": "Compressor Overheating",
                    "status": "Current",
                    "confidence_score": 93,
                    "root_cause": "Discharge line temperature is extremely high (97.0 °C), indicating potential thermal strain inside the compressor.",
                    "severity": "High",
                    "recommended_action": "Inspect the condenser fan and clean the condenser coils."
                }
            ]
        }
    },
    {
        "fault": "Excessive Compressor Vibration and Dust Accumulation",
        "ac_unit": "AC4",
        "base_telemetry": {
            "dust_sensor": 436.0,      # High dust (> 340 µg/m³)
            "dht_temp": 26.9,          # Elevated supply air temperature (> 25 °C)
            "dht_humidity": 66.8,
            "vibration": 94.8,         # Normal / slightly high vibration
            "ds18b20_temp1": 62.5,     # Normal discharge temp
            "ds18b20_temp2": 15.9,     # Normal suction temp
            "pzem_voltage": 232.1,
            "pzem_current": 7.87,
            "pzem_power": 1794.8,
            "pzem_energy": 5.12,
            "pzem_frequency": 60.0,
            "pzem_power_factor": 0.88,
        },
        "ai_diagnoses": {
            "diagnoses": [
                {
                    "issue": "Excessive Compressor Vibration and Dust Accumulation",
                    "status": "Current",
                    "confidence_score": 93,
                    "root_cause": "High dust level (436.0 µg/m³) indicates that the filter is heavily clogged, restricting airflow and reducing heat transfer efficiency.",
                    "severity": "Low",
                    "recommended_action": "Clean/replace filter and clean evaporator coil."
                }
            ]
        }
    },
    {
        "fault": "Refrigerant leak",
        "ac_unit": "AC5",
        "base_telemetry": {
            "dust_sensor": None,
            "dht_temp": 26.0,          # High output temp (> 25 °C)
            "dht_humidity": 70.0,
            "vibration": 75.0,
            "ds18b20_temp1": 48.5,     # Low discharge temp (< 50 °C)
            "ds18b20_temp2": 19.0,     # High suction temp (> 17 °C)
            "pzem_voltage": 227.0,
            "pzem_current": 6.5,       # Low current (< 7.6 A)
            "pzem_power": 1475.0,      # Low power (< 1700 W)
            "pzem_energy": 2.14,
            "pzem_frequency": 60.0,
            "pzem_power_factor": 0.82,
        },
        "ai_diagnoses": {
            "diagnoses": [
                {
                    "issue": "Refrigerant leak",
                    "status": "Current",
                    "confidence_score": 94,
                    "root_cause": "Low current (6.5A) and low power (1475W) combined with high suction temp (19.0 °C) confirm a low refrigerant charge condition.",
                    "severity": "High",
                    "recommended_action": "Check for leaks in the coil and fittings, repair leaks, and recharge R410A."
                }
            ]
        }
    },
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
            
            # Compute current based on power and voltage
            tel["pzem_power"] = round(tel["pzem_power"] + random.uniform(-20.0, 20.0), 1)
            tel["pzem_current"] = round(tel["pzem_power"] / tel["pzem_voltage"], 2)
            
            tel["dht_temp"] = round(tel["dht_temp"] + random.uniform(-0.4, 0.4), 1)
            
            # Apply offsets to specific trigger fields
            if tel["ds18b20_temp1"] > 70.0:
                tel["ds18b20_temp1"] = round(tel["ds18b20_temp1"] + random.uniform(-2.0, 2.0), 1)
            if tel["ds18b20_temp2"] < 4.0:
                tel["ds18b20_temp2"] = round(tel["ds18b20_temp2"] + random.uniform(-0.5, 0.5), 1)
            elif tel["ds18b20_temp2"] > 17.0:
                tel["ds18b20_temp2"] = round(tel["ds18b20_temp2"] + random.uniform(-1.5, 1.5), 1)
            if tel["vibration"] > 90.0:
                tel["vibration"] = round(tel["vibration"] + random.uniform(-5.0, 5.0), 1)
                
            # Add ac_unit label to the context
            tel["ac_unit"] = tmpl["ac_unit"]
            
            # Run the rule engine dynamically
            rule_result = analyze_with_rules(tel)
            
            # Combine rule diagnoses and AI diagnoses
            combined = json.dumps({
                "rule_diagnoses": rule_result,
                "ai_diagnoses": tmpl["ai_diagnoses"]
            })
            
            # Build short summary text
            findings = rule_result["findings"]
            high_findings = [f for f in findings if f["severity"] in ("High", "Critical")]
            
            summary_lines = [f"[RULE ENGINE] !! AC Diagnostic Alert ({tmpl['ac_unit']}) !!"]
            for f in high_findings[:2]:
                parts = [p.strip() for p in f["recommended_action"].split(". ") if p.strip()]
                action_short = f"{parts[0]}." if parts else "Inspect unit."
                summary_lines.append(f"\n[{f['severity'].upper()}] {f['issue']}\nAction: {action_short}")
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
