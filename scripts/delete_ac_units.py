#!/usr/bin/env python3
import sys
import json
from pathlib import Path

# Add the parent directory of this script to the Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from database import get_db_connection

TARGET_UNITS = ('AC6', 'AC7', 'AC9', 'AC10')

def delete_units():
    print("Connecting to the database...")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        return

    try:
        # 1. Delete from data_gathered
        print(f"Deleting records for {TARGET_UNITS} from data_gathered...")
        cur.execute(
            "DELETE FROM data_gathered WHERE ac_unit IN %s",
            (TARGET_UNITS,)
        )
        deleted_gathered = cur.rowcount
        print(f"Deleted {deleted_gathered} records from data_gathered.")

        # 2. Delete from alerts
        # We need to filter alerts that belong to these units.
        # Since the unit is stored in the json field of diagnoses (e.g. {"rule_diagnoses": {"ac_unit": "AC6"}}) 
        # or summarized in the summary (e.g. "[RULE ENGINE] !! AC Diagnostic Alert (AC6) !!")
        print(f"Deleting alerts associated with {TARGET_UNITS}...")
        cur.execute(
            """
            DELETE FROM alerts 
            WHERE summary LIKE '%%(AC6)%%' 
               OR summary LIKE '%%(AC7)%%' 
               OR summary LIKE '%%(AC9)%%' 
               OR summary LIKE '%%(AC10)%%'
            """
        )
        deleted_alerts = cur.rowcount
        print(f"Deleted {deleted_alerts} records from alerts.")

        conn.commit()
        print("Database cleanup completed successfully!")

    except Exception as e:
        print(f"An error occurred: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    delete_units()
