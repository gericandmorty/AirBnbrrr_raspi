#!/usr/bin/env python3
import sys, random
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from database import get_db_connection

def update_ac5_dust():
    print("Connecting to database...")
    conn = get_db_connection()
    cur  = conn.cursor()

    cur.execute("SELECT id FROM data_gathered WHERE ac_unit = 'AC5'")
    rows = cur.fetchall()
    print(f"Updating dust_sensor for {len(rows)} AC5 records (30% = 0.00, 70% = 1–200)...")

    for r in rows:
        # 30% chance of exactly 0.00, otherwise random 1–200
        val = 0.00 if random.random() < 0.30 else round(random.uniform(1.0, 200.0), 2)
        cur.execute("UPDATE data_gathered SET dust_sensor = %s WHERE id = %s", (val, r['id']))

    conn.commit()
    conn.close()
    print("Done!")

if __name__ == "__main__":
    update_ac5_dust()
