#!/usr/bin/env python3
import sys
from pathlib import Path

# Add the parent directory of this script to the Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from database import get_db_connection

def clear_ac3_dust():
    print("Connecting to the database...")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        return

    try:
        print("Updating 'data_gathered' to set dust_sensor = 0.00 for AC3...")
        cur.execute(
            "UPDATE data_gathered SET dust_sensor = 0.00 WHERE ac_unit = %s",
            ("AC3",)
        )
        count = cur.rowcount
        conn.commit()
        print(f"Successfully set dust_sensor = 0.00 for {count} records in AC3!")
    except Exception as e:
        print(f"An error occurred: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    clear_ac3_dust()
