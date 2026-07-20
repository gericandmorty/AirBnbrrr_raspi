#!/usr/bin/env python3
import sys
import random
from pathlib import Path

# Add the parent directory of this script to the Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from database import get_db_connection

def randomize_ac4_dust():
    print("Connecting to the database...")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        return

    try:
        print("Fetching AC4 rows from data_gathered...")
        cur.execute("SELECT id FROM data_gathered WHERE ac_unit = 'AC4'")
        rows = cur.fetchall()
        
        if not rows:
            print("No data_gathered records found for AC4.")
            return
            
        print(f"Randomizing dust levels for {len(rows)} records of AC4...")
        for r in rows:
            row_id = r['id']
            # 10% chance of being 0.00, otherwise random between 1.0 and 600.0 µg/m³
            if random.random() < 0.10:
                val = 0.00
            else:
                val = round(random.uniform(1.0, 600.0), 2)
            cur.execute(
                "UPDATE data_gathered SET dust_sensor = %s WHERE id = %s",
                (val, row_id)
            )
            
        conn.commit()
        print("Successfully randomized AC4 dust levels!")
        
    except Exception as e:
        print(f"An error occurred: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    randomize_ac4_dust()
