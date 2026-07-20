#!/usr/bin/env python3
import sys
import random
from pathlib import Path

# Add the parent directory of this script to the Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from database import get_db_connection

# The list of 50 dust sensor reading values you provided
DUST_VALUES = [
    0.0, 0.0, 14.0, 0.0, 0.0, 37.0, 0.0, 0.0, 0.0, 22.0,
    0.0, 0.0, 0.0, 48.0, 0.0, 0.0, 65.0, 0.0, 0.0, 31.0,
    0.0, 0.0, 0.0, 0.0, 18.0, 0.0, 0.0, 0.0, 153.0, 0.0,
    0.0, 42.0, 0.0, 0.0, 0.0, 76.0, 0.0, 0.0, 11.0, 0.0,
    0.0, 0.0, 0.0, 56.0, 0.0, 0.0, 24.0, 0.0, 187.0, 0.0
]

def update_dust():
    print("Connecting to the database...")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        return

    try:
        # Fetch all ids for AC2 in data_gathered
        cur.execute("SELECT id FROM data_gathered WHERE ac_unit = %s", ("AC2",))
        rows = cur.fetchall()
        count = len(rows)
        print(f"Found {count} records in 'data_gathered' for ac_unit='AC2'.")
        
        if count == 0:
            print("No records found to update.")
            return

        print("Updating records with randomized dust_sensor values from the pool...")
        for row in rows:
            row_id = row['id']
            # Choose a random value from the list
            random_dust = random.choice(DUST_VALUES)
            cur.execute(
                "UPDATE data_gathered SET dust_sensor = %s WHERE id = %s",
                (random_dust, row_id)
            )
        
        conn.commit()
        print("All matching records updated successfully!")
    except Exception as e:
        print(f"An error occurred: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    update_dust()
