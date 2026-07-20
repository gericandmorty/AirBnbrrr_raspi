#!/usr/bin/env python3
import sys
from pathlib import Path

# Add the parent directory of this script to the Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from database import get_db_connection

def make_ac5_dust_healthy():
    print("Connecting to the database...")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        return

    try:
        print("Setting all dust_sensor (air quality) readings for AC5 to 0.00...")
        cur.execute(
            "UPDATE data_gathered SET dust_sensor = 0.00 WHERE ac_unit = 'AC5'"
        )
        updated_count = cur.rowcount
        conn.commit()
        print(f"Successfully updated {updated_count} records for AC5!")

    except Exception as e:
        print(f"An error occurred: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    make_ac5_dust_healthy()
