#!/usr/bin/env python3
import os
import sys
import json
from pathlib import Path

# Add the parent directory of this script to the python path to load database.py and services
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

try:
    from database import get_db_connection
    from services.rule_engine import analyze_with_rules
except ImportError as e:
    print(f"Error importing modules: {e}")
    sys.exit(1)

def run_historical_alerts_migration():
    print("Connecting to Supabase...")
    conn = get_db_connection()
    cur = conn.cursor()

    # Query all historical data
    print("Fetching historical data records...")
    cur.execute("SELECT * FROM historical_data ORDER BY date ASC")
    rows = cur.fetchall()

    print(f"Fetched {len(rows)} records. Processing through rule engine...")

    alerts_created = 0

    insert_sql = """
        INSERT INTO alerts (timestamp, summary, diagnoses)
        VALUES (%(timestamp)s, %(summary)s, %(diagnoses)s)
    """

    for r in rows:
        date_obj = r["date"]
        # Convert date to string for database query if needed, or date object directly works
        date_str = date_obj.isoformat() if hasattr(date_obj, 'isoformat') else str(date_obj)

        # Convert row values into a dictionary of floats/strings for the rule engine
        telemetry_payload = {}
        for key, val in r.items():
            if key == "date":
                continue
            # Try to convert values to numeric float where appropriate
            if val is not None:
                try:
                    telemetry_payload[key] = float(val)
                except ValueError:
                    telemetry_payload[key] = str(val).strip()

        # Run the rule engine
        rule_result = analyze_with_rules(telemetry_payload)

        # If any findings are triggered, create an alert
        if rule_result["findings"]:
            # Format the summary/alerts
            findings_str = []
            for f in rule_result["findings"]:
                findings_str.append(f"[{f['severity']}] {f['issue']}")
            
            summary_msg = f"[HISTORICAL ALARM] {', '.join(findings_str)}"
            
            # Diagnoses payload combining rule engine and mock AI diagnoses
            combined_diagnoses = json.dumps({
                "rule_diagnoses": rule_result,
                "ai_diagnoses": {
                    "note": "AI layer diagnosis was bypassed for bulk historical back-migration."
                }
            })

            # Backdate the alert to the historical date
            alert_timestamp = f"{date_str} 00:00:00"

            # Execute insert
            cur.execute(insert_sql, {
                "timestamp": alert_timestamp,
                "summary": summary_msg,
                "diagnoses": combined_diagnoses
            })
            alerts_created += 1

    conn.commit()
    cur.close()
    conn.close()

    print(f"\nHistorical alert back-run complete!")
    print(f"Total alerts generated and stored in Supabase: {alerts_created}")

if __name__ == "__main__":
    run_historical_alerts_migration()
