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

# Predefined fault signatures based on the specs table
FAULT_TEMPLATES = [
    {
        "fault": "Condenser overload",
        "ac_unit": "AC2",
        "base_telemetry": {
            "dust_sensor": 120.0,
            "dht_temp": 23.5,
            "dht_humidity": 96.0,
            "vibration": 75.0,
            "ds18b20_temp1": 68.0,
            "ds18b20_temp2": 11.5,
            "pzem_voltage": 226.5,
            "pzem_current": 8.7,    # High (> 8.2 A)
            "pzem_power": 1850.0,   # High (> 1820 W)
            "pzem_energy": 4.12,
            "pzem_frequency": 60.0,
            "pzem_power_factor": 0.88,
        },
        "ai_diagnoses": {
            "diagnoses": [
                {
                    "issue": "Condenser Overload",
                    "status": "Current",
                    "confidence_score": 92,
                    "root_cause": "High current draw and power draw indicate the compressor motor is working under strain, likely due to a blocked or dirty condenser coil.",
                    "severity": "High",
                    "recommended_action": "Clean the condenser coil and inspect the condenser fan."
                }
            ]
        }
    },
    {
        "fault": "Dirty air filter",
        "ac_unit": "AC3",
        "base_telemetry": {
            "dust_sensor": 395.0,    # High (> 340 µg/m³)
            "dht_temp": 27.5,        # High (> 25 °C)
            "dht_humidity": 94.0,    # Low (< 95%)
            "vibration": 70.0,
            "ds18b20_temp1": 55.0,
            "ds18b20_temp2": 10.0,
            "pzem_voltage": 228.0,
            "pzem_current": 7.8,
            "pzem_power": 1740.0,
            "pzem_energy": 5.82,
            "pzem_frequency": 60.1,
            "pzem_power_factor": 0.89,
        },
        "ai_diagnoses": {
            "diagnoses": [
                {
                    "issue": "Dirty air filter",
                    "status": "Current",
                    "confidence_score": 95,
                    "root_cause": "High dust sensor reading (above 340 µg/m³) and elevated supply air temperature indicate the air filter is restricted.",
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
            "dust_sensor": 80.0,
            "dht_temp": 28.0,        # High (> 25 °C)
            "dht_humidity": 93.5,    # Low (< 95%)
            "vibration": 65.0,
            "ds18b20_temp1": 76.0,    # High (> 70 °C)
            "ds18b20_temp2": 18.5,    # High (> 17 °C)
            "pzem_voltage": 227.0,
            "pzem_current": 5.4,     # Low (< 7.6 A)
            "pzem_power": 1150.0,    # Low (< 1700 W)
            "pzem_energy": 2.14,
            "pzem_frequency": 59.9,
            "pzem_power_factor": 0.72,
        },
        "ai_diagnoses": {
            "diagnoses": [
                {
                    "issue": "Refrigerant leak",
                    "status": "Current",
                    "confidence_score": 94,
                    "root_cause": "Operating current and power are low while discharge temperature is elevated, which is a key signature of low refrigerant charge.",
                    "severity": "High",
                    "recommended_action": "Check for leaks in the coil and fittings, repair leaks, and recharge R410A."
                }
            ]
        }
    },
    {
        "fault": "Compressor mechanical damage",
        "ac_unit": "AC6",
        "base_telemetry": {
            "dust_sensor": 50.0,
            "dht_temp": 24.5,
            "dht_humidity": 97.0,
            "vibration": 115.0,      # High (> 90 Hz)
            "ds18b20_temp1": 84.0,    # High (> 70 °C)
            "ds18b20_temp2": 12.0,
            "pzem_voltage": 225.5,
            "pzem_current": 8.9,     # High (> 8.2 A)
            "pzem_power": 1890.0,    # High (> 1820 W)
            "pzem_energy": 9.15,
            "pzem_frequency": 60.0,
            "pzem_power_factor": 0.87,
        },
        "ai_diagnoses": {
            "diagnoses": [
                {
                    "issue": "Compressor mechanical damage",
                    "status": "Current",
                    "confidence_score": 90,
                    "root_cause": "High compressor vibration (> 90 Hz) and elevated current draw indicate potential mechanical wear or loose mounting.",
                    "severity": "High",
                    "recommended_action": "Check/Inspect the compressor wirings and internals."
                }
            ]
        }
    },
    {
        "fault": "Capacitor degradation",
        "ac_unit": "AC1",
        "base_telemetry": {
            "dust_sensor": 10.0,
            "dht_temp": 23.0,
            "dht_humidity": 98.0,
            "vibration": 45.0,       # Low (< 60 Hz)
            "ds18b20_temp1": 52.0,
            "ds18b20_temp2": 9.0,
            "pzem_voltage": 227.5,
            "pzem_current": 8.6,     # High (> 8.2 A)
            "pzem_power": 1840.0,    # High (> 1820 W)
            "pzem_energy": 3.75,
            "pzem_frequency": 60.0,
            "pzem_power_factor": 0.74,  # Low (< 0.85)
        },
        "ai_diagnoses": {
            "diagnoses": [
                {
                    "issue": "Capacitor failure",
                    "status": "Current",
                    "confidence_score": 87,
                    "root_cause": "High current and power factor below 0.85 indicate the start/run capacitor has degraded.",
                    "severity": "High",
                    "recommended_action": "Test capacitor with a capacitance meter and replace if needed."
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
        
        print("Generating 35 alerts from July 9 to July 20, 2026 (excluding weekends)...")
        LOCAL_TZ = timezone(timedelta(hours=8))
        
        for i in range(35):
            # Select target day by cycling through the weekdays
            day = WEEKDAYS[i % len(WEEKDAYS)]
            
            # Select random fault template
            tmpl = random.choice(FAULT_TEMPLATES)
            
            # Copy telemetry and apply small random variations to make data authentic
            tel = dict(tmpl["base_telemetry"])
            tel["pzem_voltage"] = round(tel["pzem_voltage"] + random.uniform(-1.5, 1.5), 1)
            tel["pzem_current"] = round(tel["pzem_current"] + random.uniform(-0.15, 0.15), 2)
            tel["pzem_power"] = round(tel["pzem_power"] + random.uniform(-25.0, 25.0), 1)
            tel["dht_temp"] = round(tel["dht_temp"] + random.uniform(-0.5, 0.5), 1)
            
            if tel["dust_sensor"] > 100:
                tel["dust_sensor"] = round(tel["dust_sensor"] + random.uniform(-15.0, 15.0), 1)
            if tel["vibration"] > 0:
                tel["vibration"] = round(tel["vibration"] + random.uniform(-3.0, 3.0), 1)
                
            # Add ac_unit label to the rule evaluation context
            tel["ac_unit"] = tmpl["ac_unit"]
            
            # Run the rule engine dynamically on the telemetry
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
            
            # Insert into alerts database table
            cur.execute(
                "INSERT INTO alerts (timestamp, summary, diagnoses) VALUES (%s, %s, %s)",
                (alert_time, summary, combined)
            )
            
        conn.commit()
        print("Successfully generated and seeded 35 alerts into the database!")
    except Exception as e:
        print(f"An error occurred: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    seed_alerts()
