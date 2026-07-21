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
        "day": 14,
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
        "day": 9,
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
        "day": 9,
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
        "fault": "Reduced Cooling Performance",
        "ac_unit": "AC5",
        "day": 13,
        "base_telemetry": {
            "dust_sensor": 95.0,
            "dht_temp": 22.0,           # Output air temp >= 21°C (triggers rule)
            "dht_humidity": 74.0,       # Normal (<= 80%)
            "vibration": 72.0,          # Normal (< 90 Hz)
            "ds18b20_temp1": 66.0,      # Outlet compressor >= 64°C (triggers rule)
            "ds18b20_temp2": 24.5,      # Inlet >= 22°C AND ~2-3°C above output (triggers rule)
            "pzem_voltage": 228.0,
            "pzem_current": 7.8,
            "pzem_power": 1750.0,
            "pzem_frequency": 60.0,
            "pzem_power_factor": 0.88,
        },
        "ai_diagnoses": {
            "diagnoses": [
                {
                    "issue": "Reduced Cooling Performance",
                    "status": "Current",
                    "confidence_score": 92,
                    "root_cause": "Outlet and inlet/suction temperatures are unusually close together (inlet ~2–3 °C above output), and compressor outlet temp is elevated, indicating insufficient refrigerant charge reducing heat exchange and cooling efficiency.",
                    "severity": "Medium",
                    "recommended_action": "The monitored temperatures indicate a reduction in cooling performance. Inspect the refrigerant system for possible refrigerant leakage or insufficient refrigerant charge. Verify the condition using appropriate refrigeration service equipment and perform corrective maintenance if necessary."
                }
            ]
        }
    },
    {
        "fault": "High Voltage",
        "ac_unit": "AC1",
        "day": 6,
        "base_telemetry": {
            "dust_sensor": 45.0,
            "dht_temp": 18.0,
            "dht_humidity": 55.0,
            "vibration": 45.0,
            "ds18b20_temp1": 55.0,
            "ds18b20_temp2": 12.0,
            "pzem_voltage": 244.0,     # Triggers voltage > 241
            "pzem_current": 8.0,
            "pzem_power": 1750.0,
            "pzem_frequency": 60.0,
            "pzem_power_factor": 0.88,
        },
        "ai_diagnoses": {
            "diagnoses": [
                {
                    "issue": "High Voltage - Overvoltage supply",
                    "status": "Current",
                    "confidence_score": 94,
                    "root_cause": "Voltage supply (244.0 V) is outside the safe operating range of 225–241 V.",
                    "severity": "High",
                    "recommended_action": "Verify input voltage stability and check voltage regulator status."
                }
            ]
        }
    },
    {
        "fault": "Low Voltage",
        "ac_unit": "AC1",
        "day": 6,
        "base_telemetry": {
            "dust_sensor": 45.0,
            "dht_temp": 18.0,
            "dht_humidity": 55.0,
            "vibration": 45.0,
            "ds18b20_temp1": 55.0,
            "ds18b20_temp2": 12.0,
            "pzem_voltage": 222.0,     # Triggers voltage < 225
            "pzem_current": 8.0,
            "pzem_power": 1750.0,
            "pzem_frequency": 60.0,
            "pzem_power_factor": 0.88,
        },
        "ai_diagnoses": {
            "diagnoses": [
                {
                    "issue": "Low Voltage - Undervoltage supply",
                    "status": "Current",
                    "confidence_score": 94,
                    "root_cause": "Voltage supply (222.0 V) is outside the safe operating range of 225–241 V.",
                    "severity": "High",
                    "recommended_action": "Verify input voltage stability and check voltage regulator status."
                }
            ]
        }
    },
    {
        "fault": "High Current Anomaly",
        "ac_unit": "AC2",
        "day": 7,
        "base_telemetry": {
            "dust_sensor": 45.0,
            "dht_temp": 18.0,
            "dht_humidity": 55.0,
            "vibration": 45.0,
            "ds18b20_temp1": 55.0,
            "ds18b20_temp2": 12.0,
            "pzem_voltage": 228.0,
            "pzem_current": 9.2,       # Triggers current outside 7.6-8.8
            "pzem_power": 1750.0,
            "pzem_frequency": 60.0,
            "pzem_power_factor": 0.88,
        },
        "ai_diagnoses": {
            "diagnoses": [
                {
                    "issue": "High Current Anomaly",
                    "status": "Current",
                    "confidence_score": 93,
                    "root_cause": "Current draw (9.2 A) is outside the safe operating range of 7.6–8.8 A.",
                    "severity": "High",
                    "recommended_action": "Inspect electrical wiring, connections, and check compressor motor draws."
                }
            ]
        }
    },
    {
        "fault": "Low Current Anomaly",
        "ac_unit": "AC2",
        "day": 7,
        "base_telemetry": {
            "dust_sensor": 45.0,
            "dht_temp": 18.0,
            "dht_humidity": 55.0,
            "vibration": 45.0,
            "ds18b20_temp1": 55.0,
            "ds18b20_temp2": 12.0,
            "pzem_voltage": 228.0,
            "pzem_current": 7.2,       # Triggers current outside 7.6-8.8
            "pzem_power": 1750.0,
            "pzem_frequency": 60.0,
            "pzem_power_factor": 0.88,
        },
        "ai_diagnoses": {
            "diagnoses": [
                {
                    "issue": "Low Current Anomaly",
                    "status": "Current",
                    "confidence_score": 93,
                    "root_cause": "Current draw (7.2 A) is outside the safe operating range of 7.6–8.8 A.",
                    "severity": "High",
                    "recommended_action": "Inspect electrical wiring and check compressor loading."
                }
            ]
        }
    },
    {
        "fault": "High Power Anomaly",
        "ac_unit": "AC2",
        "day": 7,
        "base_telemetry": {
            "dust_sensor": 45.0,
            "dht_temp": 18.0,
            "dht_humidity": 55.0,
            "vibration": 45.0,
            "ds18b20_temp1": 55.0,
            "ds18b20_temp2": 12.0,
            "pzem_voltage": 228.0,
            "pzem_current": 8.0,
            "pzem_power": 1890.0,      # Triggers power outside 1650-1860
            "pzem_frequency": 60.0,
            "pzem_power_factor": 0.88,
        },
        "ai_diagnoses": {
            "diagnoses": [
                {
                    "issue": "High Power Anomaly",
                    "status": "Current",
                    "confidence_score": 93,
                    "root_cause": "Power draw (1890.0 W) is outside the safe operating range of 1650–1860 W.",
                    "severity": "High",
                    "recommended_action": "Check compressor electrical loading and verify line stability."
                }
            ]
        }
    },
    {
        "fault": "Low Power Anomaly",
        "ac_unit": "AC2",
        "day": 7,
        "base_telemetry": {
            "dust_sensor": 45.0,
            "dht_temp": 18.0,
            "dht_humidity": 55.0,
            "vibration": 45.0,
            "ds18b20_temp1": 55.0,
            "ds18b20_temp2": 12.0,
            "pzem_voltage": 228.0,
            "pzem_current": 8.0,
            "pzem_power": 1620.0,      # Triggers power outside 1650-1860
            "pzem_frequency": 60.0,
            "pzem_power_factor": 0.88,
        },
        "ai_diagnoses": {
            "diagnoses": [
                {
                    "issue": "Low Power Anomaly",
                    "status": "Current",
                    "confidence_score": 93,
                    "root_cause": "Power draw (1620.0 W) is outside the safe operating range of 1650–1860 W.",
                    "severity": "High",
                    "recommended_action": "Check line voltage stability and compressor capacitors."
                }
            ]
        }
    },
    {
        "fault": "High Output Temp Anomaly",
        "ac_unit": "AC1",
        "day": 6,
        "base_telemetry": {
            "dust_sensor": 45.0,
            "dht_temp": 27.5,          # Triggers dht_temp outside 7-25
            "dht_humidity": 55.0,
            "vibration": 45.0,
            "ds18b20_temp1": 55.0,
            "ds18b20_temp2": 12.0,
            "pzem_voltage": 228.0,
            "pzem_current": 8.0,
            "pzem_power": 1750.0,
            "pzem_frequency": 60.0,
            "pzem_power_factor": 0.88,
        },
        "ai_diagnoses": {
            "diagnoses": [
                {
                    "issue": "High Output Temp Anomaly",
                    "status": "Current",
                    "confidence_score": 92,
                    "root_cause": "Supply air output temperature (27.5 °C) is outside the safe operating range of 7–25 °C.",
                    "severity": "High",
                    "recommended_action": "Inspect evaporator fan, clean filter, and check for correct air discharge."
                }
            ]
        }
    },
    {
        "fault": "Low Output Temp Anomaly",
        "ac_unit": "AC1",
        "day": 6,
        "base_telemetry": {
            "dust_sensor": 45.0,
            "dht_temp": 5.0,          # Triggers dht_temp outside 7-25
            "dht_humidity": 55.0,
            "vibration": 45.0,
            "ds18b20_temp1": 55.0,
            "ds18b20_temp2": 12.0,
            "pzem_voltage": 228.0,
            "pzem_current": 8.0,
            "pzem_power": 1750.0,
            "pzem_frequency": 60.0,
            "pzem_power_factor": 0.88,
        },
        "ai_diagnoses": {
            "diagnoses": [
                {
                    "issue": "Low Output Temp Anomaly",
                    "status": "Current",
                    "confidence_score": 92,
                    "root_cause": "Supply air output temperature (5.0 °C) is outside the safe operating range of 7–25 °C.",
                    "severity": "High",
                    "recommended_action": "Inspect evaporator for frost buildup, verify fan operation."
                }
            ]
        }
    },
    {
        "fault": "Humidity Anomaly",
        "ac_unit": "AC2",
        "day": 7,
        "base_telemetry": {
            "dust_sensor": 45.0,
            "dht_temp": 18.0,
            "dht_humidity": 85.0,      # Triggers humidity > 80%
            "vibration": 45.0,
            "ds18b20_temp1": 55.0,
            "ds18b20_temp2": 12.0,
            "pzem_voltage": 228.0,
            "pzem_current": 8.0,
            "pzem_power": 1750.0,
            "pzem_frequency": 60.0,
            "pzem_power_factor": 0.88,
        },
        "ai_diagnoses": {
            "diagnoses": [
                {
                    "issue": "Humidity Anomaly",
                    "status": "Current",
                    "confidence_score": 91,
                    "root_cause": "Relative humidity (85.0%) exceeds the normal operating limit of 80%.",
                    "severity": "Low",
                    "recommended_action": "Verify indoor fan speeds, check return air humidity, and confirm condensate drainage."
                }
            ]
        }
    },
    {
        "fault": "High Outlet Temperature",
        "ac_unit": "AC3",
        "day": 14,
        "base_telemetry": {
            "dust_sensor": 45.0,
            "dht_temp": 18.0,
            "dht_humidity": 55.0,
            "vibration": 45.0,
            "ds18b20_temp1": 74.5,     # Triggers ds18b20_temp1 outside 50-70
            "ds18b20_temp2": 12.0,
            "pzem_voltage": 228.0,
            "pzem_current": 8.0,
            "pzem_power": 1750.0,
            "pzem_frequency": 60.0,
            "pzem_power_factor": 0.88,
        },
        "ai_diagnoses": {
            "diagnoses": [
                {
                    "issue": "High Outlet Temperature (Discharge) — Dirty condenser coil",
                    "status": "Current",
                    "confidence_score": 93,
                    "root_cause": "Outlet compressor discharge line temperature (74.5 °C) is outside the safe operating range of 50–70 °C.",
                    "severity": "High",
                    "recommended_action": "Check whether the condenser fan is operating properly. Stop operating the air conditioner if the current continues to increase to prevent compressor damage and protect the electrical wiring and circuit breaker."
                }
            ]
        }
    },
    {
        "fault": "Low Outlet Temperature",
        "ac_unit": "AC3",
        "day": 14,
        "base_telemetry": {
            "dust_sensor": 45.0,
            "dht_temp": 18.0,
            "dht_humidity": 55.0,
            "vibration": 45.0,
            "ds18b20_temp1": 44.5,     # Triggers ds18b20_temp1 outside 50-70
            "ds18b20_temp2": 12.0,
            "pzem_voltage": 228.0,
            "pzem_current": 8.0,
            "pzem_power": 1750.0,
            "pzem_frequency": 60.0,
            "pzem_power_factor": 0.88,
        },
        "ai_diagnoses": {
            "diagnoses": [
                {
                    "issue": "Low Outlet Temperature (Discharge) — Low refrigerant charge",
                    "status": "Current",
                    "confidence_score": 93,
                    "root_cause": "Outlet compressor discharge line temperature (44.5 °C) is outside the safe operating range of 50–70 °C.",
                    "severity": "High",
                    "recommended_action": "Check compressor operation and verify system refrigerant level."
                }
            ]
        }
    },
    {
        "fault": "High Inlet Temperature",
        "ac_unit": "AC3",
        "day": 14,
        "base_telemetry": {
            "dust_sensor": 45.0,
            "dht_temp": 18.0,
            "dht_humidity": 55.0,
            "vibration": 45.0,
            "ds18b20_temp1": 55.0,
            "ds18b20_temp2": 19.5,     # Triggers ds18b20_temp2 outside 8-17
            "pzem_voltage": 228.0,
            "pzem_current": 8.0,
            "pzem_power": 1750.0,
            "pzem_frequency": 60.0,
            "pzem_power_factor": 0.88,
        },
        "ai_diagnoses": {
            "diagnoses": [
                {
                    "issue": "High Inlet Temperature (Suction) — Dirty evaporator coil",
                    "status": "Current",
                    "confidence_score": 93,
                    "root_cause": "Inlet compressor suction line temperature (19.5 °C) is outside the safe operating range of 8–17 °C.",
                    "severity": "High",
                    "recommended_action": "Inspect suction line insulation, check expansion valve operation, and verify refrigerant charge."
                }
            ]
        }
    },
    {
        "fault": "Low Inlet Temperature",
        "ac_unit": "AC3",
        "day": 14,
        "base_telemetry": {
            "dust_sensor": 45.0,
            "dht_temp": 18.0,
            "dht_humidity": 55.0,
            "vibration": 45.0,
            "ds18b20_temp1": 55.0,
            "ds18b20_temp2": 5.5,     # Triggers ds18b20_temp2 outside 8-17
            "pzem_voltage": 228.0,
            "pzem_current": 8.0,
            "pzem_power": 1750.0,
            "pzem_frequency": 60.0,
            "pzem_power_factor": 0.88,
        },
        "ai_diagnoses": {
            "diagnoses": [
                {
                    "issue": "Low Inlet Temperature (Suction) — faulty thermostat",
                    "status": "Current",
                    "confidence_score": 93,
                    "root_cause": "Inlet compressor suction line temperature (5.5 °C) is outside the safe operating range of 8–17 °C.",
                    "severity": "High",
                    "recommended_action": "Inspect suction line insulation, check expansion valve operation, and verify refrigerant charge."
                }
            ]
        }
    },
    {
        "fault": "Low Vibration",
        "ac_unit": "AC4",
        "day": 9,
        "base_telemetry": {
            "dust_sensor": 45.0,
            "dht_temp": 18.0,
            "dht_humidity": 55.0,
            "vibration": 5.0,         # Triggers vibration < 10
            "ds18b20_temp1": 55.0,
            "ds18b20_temp2": 12.0,
            "pzem_voltage": 228.0,
            "pzem_current": 8.0,
            "pzem_power": 1750.0,
            "pzem_frequency": 60.0,
            "pzem_power_factor": 0.88,
        },
        "ai_diagnoses": {
            "diagnoses": [
                {
                    "issue": "Low Vibration — Compressor not operating, fan not running or off",
                    "status": "Current",
                    "confidence_score": 95,
                    "root_cause": "Vibration frequency is abnormally low, suggesting the unit is not running or operating.",
                    "severity": "High",
                    "recommended_action": "Verify power supply to compressor and fan; check starter capacitors and contactors."
                }
            ]
        }
    },
    {
        "fault": "Excessive Vibration",
        "ac_unit": "AC4",
        "day": 9,
        "base_telemetry": {
            "dust_sensor": 45.0,
            "dht_temp": 18.0,
            "dht_humidity": 55.0,
            "vibration": 92.0,         # Triggers vibration >= 90
            "ds18b20_temp1": 55.0,
            "ds18b20_temp2": 12.0,
            "pzem_voltage": 228.0,
            "pzem_current": 8.0,
            "pzem_power": 1750.0,
            "pzem_frequency": 60.0,
            "pzem_power_factor": 0.88,
        },
        "ai_diagnoses": {
            "diagnoses": [
                {
                    "issue": "Excessive Vibration — Loose compressor mounting, worn bearings, condenser fan imbalance",
                    "status": "Current",
                    "confidence_score": 93,
                    "root_cause": "Vibration frequency exceeds the safety threshold of 90 Hz.",
                    "severity": "Medium",
                    "recommended_action": "Inspect the compressor mounting, internal components, and check for signs of compressor wear or mechanical looseness."
                }
            ]
        }
    },
    {
        "fault": "Low Dust Sensor",
        "ac_unit": "AC4",
        "day": 9,
        "base_telemetry": {
            "dust_sensor": 0.0,         # Triggers dust <= 0.001
            "dht_temp": 18.0,
            "dht_humidity": 55.0,
            "vibration": 45.0,
            "ds18b20_temp1": 55.0,
            "ds18b20_temp2": 12.0,
            "pzem_voltage": 228.0,
            "pzem_current": 8.0,
            "pzem_power": 1750.0,
            "pzem_frequency": 60.0,
            "pzem_power_factor": 0.88,
        },
        "ai_diagnoses": {
            "diagnoses": [
                {
                    "issue": "Low Dust Sensor — Clean air path, recently cleaned filter, or possible dust sensor malfunction if consistently zero",
                    "status": "Current",
                    "confidence_score": 92,
                    "root_cause": "Dust concentration reading is exactly zero, which may indicate a recently cleaned filter or a sensor malfunction.",
                    "severity": "Low",
                    "recommended_action": "Check dust sensor calibration and verify clean air path."
                }
            ]
        }
    },
    {
        "fault": "Excessive Dust Sensor",
        "ac_unit": "AC4",
        "day": 9,
        "base_telemetry": {
            "dust_sensor": 355.0,         # Triggers dust >= 340
            "dht_temp": 18.0,
            "dht_humidity": 55.0,
            "vibration": 45.0,
            "ds18b20_temp1": 55.0,
            "ds18b20_temp2": 12.0,
            "pzem_voltage": 228.0,
            "pzem_current": 8.0,
            "pzem_power": 1750.0,
            "pzem_frequency": 60.0,
            "pzem_power_factor": 0.88,
        },
        "ai_diagnoses": {
            "diagnoses": [
                {
                    "issue": "Excessive Dust Sensor — Dirty air filter",
                    "status": "Current",
                    "confidence_score": 93,
                    "root_cause": "Dust concentration exceeds the safe threshold of 340 µg/m³.",
                    "severity": "Low",
                    "recommended_action": "Clean the air filter and inspect the evaporator section for dust accumulation that may restrict airflow."
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
            # Select anomalous template cycling through the templates
            tmpl = ANOMALOUS_AC_TEMPLATES[i % len(ANOMALOUS_AC_TEMPLATES)]
            day = tmpl["day"]
            
            # Copy telemetry and apply safe variations to make data authentic without clearing anomalies
            tel = dict(tmpl["base_telemetry"])
            
            # Voltage
            tel["pzem_voltage"] = tel["pzem_voltage"] + random.uniform(-1.0, 1.0)
            if tmpl["base_telemetry"]["pzem_voltage"] > 241.0:
                tel["pzem_voltage"] = max(tel["pzem_voltage"], 241.1)
            elif tmpl["base_telemetry"]["pzem_voltage"] < 225.0:
                tel["pzem_voltage"] = min(tel["pzem_voltage"], 224.9)
            tel["pzem_voltage"] = round(tel["pzem_voltage"], 1)
            
            # Current
            tel["pzem_current"] = tel["pzem_current"] + random.uniform(-0.1, 0.1)
            if tmpl["base_telemetry"]["pzem_current"] > 8.8:
                tel["pzem_current"] = max(tel["pzem_current"], 8.81)
            elif tmpl["base_telemetry"]["pzem_current"] < 7.6:
                tel["pzem_current"] = min(tel["pzem_current"], 7.59)
            tel["pzem_current"] = round(tel["pzem_current"], 2)
            
            # Power
            tel["pzem_power"] = tel["pzem_power"] + random.uniform(-10.0, 10.0)
            if tmpl["base_telemetry"]["pzem_power"] > 1860.0:
                tel["pzem_power"] = max(tel["pzem_power"], 1861.0)
            elif tmpl["base_telemetry"]["pzem_power"] < 1650.0:
                tel["pzem_power"] = min(tel["pzem_power"], 1649.0)
            tel["pzem_power"] = round(tel["pzem_power"], 1)
            
            # Output Temp (dht_temp)
            tel["dht_temp"] = tel["dht_temp"] + random.uniform(-0.4, 0.4)
            if tmpl["base_telemetry"]["dht_temp"] > 25.0:
                tel["dht_temp"] = max(tel["dht_temp"], 25.1)
            elif tmpl["base_telemetry"]["dht_temp"] < 7.0:
                tel["dht_temp"] = min(tel["dht_temp"], 6.9)
            tel["dht_temp"] = round(tel["dht_temp"], 1)
            
            # Humidity (dht_humidity)
            tel["dht_humidity"] = tel["dht_humidity"] + random.uniform(-2.0, 2.0)
            if tmpl["base_telemetry"]["dht_humidity"] > 80.0:
                tel["dht_humidity"] = max(tel["dht_humidity"], 80.1)
            tel["dht_humidity"] = round(tel["dht_humidity"], 1)
            
            # Vibration
            tel["vibration"] = tel["vibration"] + random.uniform(-3.0, 3.0)
            if tmpl["base_telemetry"]["vibration"] >= 90.0:
                tel["vibration"] = max(tel["vibration"], 90.1)
            tel["vibration"] = round(tel["vibration"], 1)
            
            # Dust
            tel["dust_sensor"] = tel["dust_sensor"] + random.uniform(-5.0, 5.0)
            if tmpl["base_telemetry"]["dust_sensor"] > 340.0:
                tel["dust_sensor"] = max(tel["dust_sensor"], 340.1)
            tel["dust_sensor"] = round(max(tel["dust_sensor"], 0.0), 1)

            # Outlet Compressor Temp (ds18b20_temp1)
            tel["ds18b20_temp1"] = tel["ds18b20_temp1"] + random.uniform(-1.0, 1.0)
            if tmpl["base_telemetry"]["ds18b20_temp1"] > 70.0:
                tel["ds18b20_temp1"] = max(tel["ds18b20_temp1"], 70.1)
            elif tmpl["base_telemetry"]["ds18b20_temp1"] < 50.0:
                tel["ds18b20_temp1"] = min(tel["ds18b20_temp1"], 49.9)
            tel["ds18b20_temp1"] = round(tel["ds18b20_temp1"], 1)

            # Inlet Compressor Temp (ds18b20_temp2)
            tel["ds18b20_temp2"] = tel["ds18b20_temp2"] + random.uniform(-1.0, 1.0)
            if tmpl["base_telemetry"]["ds18b20_temp2"] > 17.0:
                tel["ds18b20_temp2"] = max(tel["ds18b20_temp2"], 17.1)
            elif tmpl["base_telemetry"]["ds18b20_temp2"] < 8.0:
                tel["ds18b20_temp2"] = min(tel["ds18b20_temp2"], 7.9)
            tel["ds18b20_temp2"] = round(tel["ds18b20_temp2"], 1)
                
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
