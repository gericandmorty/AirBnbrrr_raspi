#!/usr/bin/env python3
import sys
import json
import datetime
from datetime import timedelta
from pathlib import Path

# Add the parent directory of this script to the Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from database import get_db_connection

def create_healthy_alerts():
    print("Connecting to the database...")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        return

    try:
        # Fetch the first and last timestamps for AC6 on July 20, 2026
        print("Fetching AC6 timestamps...")
        cur.execute(
            "SELECT timestamp FROM data_gathered WHERE ac_unit = 'AC6' ORDER BY timestamp ASC"
        )
        rows = cur.fetchall()
        
        if not rows:
            print("No data_gathered records found for AC6 on July 20. Cannot generate timestamps.")
            return

        first_ts = rows[0]['timestamp']
        last_ts = rows[-1]['timestamp']
        print(f"AC6 telemetry spans from {first_ts} to {last_ts}.")

        # Generate a healthy alert every 30 minutes
        current_ts = first_ts
        inserted_count = 0
        
        while current_ts <= last_ts:
            summary = f"[HEARTBEAT] !! System Status Check (AC6) !!\n\n[NORMAL] All parameters are within healthy operating guidelines.\nAction: No maintenance required. System is operating normally."
            
            diagnoses = {
                "rule_diagnoses": {
                    "overall_severity": "Normal",
                    "sensors_checked": 9,
                    "sensors_triggered": 0,
                    "computation_steps": [],
                    "findings": [],
                    "ac_unit": "AC6"
                },
                "ai_diagnoses": {
                    "diagnoses": [
                        {
                            "issue": "Normal Operation",
                            "status": "Current",
                            "confidence_score": 100,
                            "root_cause": "All physical parameters (voltage, current, power, temperature, humidity, vibration, and dust) are fully within normal operating guidelines.",
                            "severity": "Normal",
                            "recommended_action": "System is operating normally. No maintenance required."
                        }
                    ]
                }
            }
            
            cur.execute(
                "INSERT INTO alerts (timestamp, summary, diagnoses) VALUES (%s, %s, %s)",
                (current_ts, summary, json.dumps(diagnoses))
            )
            
            inserted_count += 1
            current_ts += timedelta(hours=2)
            
        conn.commit()
        print(f"Successfully created {inserted_count} healthy heartbeat alerts in the alerts table!")
        
    except Exception as e:
        print(f"An error occurred: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    create_healthy_alerts()
