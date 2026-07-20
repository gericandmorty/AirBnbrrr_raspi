#!/usr/bin/env python3
import sys
from pathlib import Path

# Add the parent directory of this script to the Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from database import get_db_connection

# Guide mapping: ac_unit -> target day in July 2026
GUIDE = {
    "AC1": 6,
    "AC2": 7,
    "AC4": 9,
    "AC5": 13,
    "AC3": 14,
    "AC6": 15,
    "AC7": 16,
}

def update_dates():
    print("Connecting to the database...")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        return

    try:
        for ac_unit, day in GUIDE.items():
            print(f"Processing unit {ac_unit} (Target date: July {day}, 2026)...")
            
            # Fetch the rows for this unit
            cur.execute(
                "SELECT id, timestamp FROM data_gathered WHERE ac_unit = %s",
                (ac_unit,)
            )
            rows = cur.fetchall()
            print(f"Found {len(rows)} records for {ac_unit}.")
            
            if len(rows) == 0:
                continue

            for r in rows:
                row_id = r['id']
                old_ts = r['timestamp']
                if old_ts:
                    # Update year, month, and day while preserving the exact time
                    new_ts = old_ts.replace(year=2026, month=7, day=day)
                    cur.execute(
                        "UPDATE data_gathered SET timestamp = %s WHERE id = %s",
                        (new_ts, row_id)
                    )
            
            conn.commit()
            print(f"Successfully updated all records for {ac_unit} to July {day}, 2026!")

        print("\nAll database updates completed successfully!")
    except Exception as e:
        print(f"An error occurred: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    update_dates()
