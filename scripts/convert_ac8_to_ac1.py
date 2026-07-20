#!/usr/bin/env python3
import sys
from pathlib import Path

# Add the parent directory of this script to the Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from database import get_db_connection

def convert_ac8_to_ac1():
    print("Connecting to the database...")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        return

    try:
        print("Converting AC8 to AC1 in 'data_gathered' table...")
        cur.execute(
            "UPDATE data_gathered SET ac_unit = %s WHERE ac_unit = %s",
            ("AC1", "AC8")
        )
        count = cur.rowcount
        conn.commit()
        print(f"Successfully converted {count} records from AC8 to AC1!")
    except Exception as e:
        print(f"An error occurred: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    convert_ac8_to_ac1()
