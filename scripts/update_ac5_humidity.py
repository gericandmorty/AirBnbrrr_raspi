#!/usr/bin/env python3
import sys, random
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from database import get_db_connection

conn = get_db_connection()
cur  = conn.cursor()
cur.execute("SELECT id FROM data_gathered WHERE ac_unit = 'AC5'")
rows = cur.fetchall()
print(f"Updating humidity for {len(rows)} AC5 records to 89–96%...")
for r in rows:
    cur.execute("UPDATE data_gathered SET dht_humidity = %s WHERE id = %s",
                (round(random.uniform(89.0, 96.0), 1), r['id']))
conn.commit()
conn.close()
print("Done!")
