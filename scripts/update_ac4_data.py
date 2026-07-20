#!/usr/bin/env python3
import sys
from pathlib import Path

# Add the parent directory of this script to the Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from database import get_db_connection

# New data provided by user
# Power, Voltage, Current, Outlet Temp, Humidity, Compressor Outlet, Inlet Temp, Vibration, Dust
NEW_DATA = [
    (2.80, 240.20, 0.04, 26.90, 66.80, 60.75, 26.81, 0.58, 0.00),
    (3.00, 240.00, 0.04, 26.80, 66.90, 60.81, 26.69, 0.71, 326.00),
    (231.40, 238.60, 0.98, 25.90, 72.60, 60.94, 25.88, 0.96, 0.00),
    (1362.80, 236.00, 5.93, 23.70, 83.40, 61.06, 23.81, 41.38, 0.00),
    (1548.60, 234.90, 6.75, 21.80, 92.80, 61.25, 22.19, 63.74, 0.00),
    (1669.40, 233.80, 7.28, 19.90, 98.60, 61.44, 20.56, 77.28, 0.00),
    (1738.20, 232.90, 7.59, 18.30, 100.00, 61.63, 19.13, 86.54, 512.00),
    (1761.70, 232.60, 7.70, 17.20, 100.00, 61.81, 18.31, 91.73, 0.00),
    (1776.40, 232.40, 7.77, 16.40, 100.00, 61.94, 17.69, 88.65, 0.00),
    (1788.60, 232.30, 7.83, 15.80, 100.00, 62.13, 17.19, 94.27, 0.00),
    (1772.90, 232.50, 7.76, 15.30, 100.00, 62.19, 16.81, 89.48, 284.00),
    (1791.40, 232.20, 7.85, 14.90, 100.00, 62.31, 16.50, 93.58, 0.00),
    (1779.30, 232.40, 7.79, 14.60, 100.00, 62.44, 16.19, 90.86, 0.00),
    (1794.80, 232.10, 7.87, 14.30, 100.00, 62.50, 15.94, 94.81, 436.00),
    (1783.60, 232.30, 7.82, 14.10, 100.00, 62.63, 15.69, 91.42, 0.00),
    (1775.90, 232.40, 7.78, 13.90, 100.00, 62.69, 15.50, 93.17, 0.00)
]

def update_ac4():
    print("Connecting to the database...")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        return

    try:
        # Fetch all AC4 rows ordered by timestamp or id
        cur.execute("SELECT id FROM data_gathered WHERE ac_unit = 'AC4' ORDER BY id ASC")
        rows = cur.fetchall()
        print(f"Found {len(rows)} records for AC4 in data_gathered.")

        if len(rows) == 0:
            print("No records found for AC4. Nothing to update.")
            return

        # Update each row with cycled values from NEW_DATA
        for i, row in enumerate(rows):
            row_id = row['id']
            # Cycle through the 16 new data rows
            data_row = NEW_DATA[i % len(NEW_DATA)]
            power, voltage, current, outlet_temp, humidity, comp_outlet, inlet_temp, vibration, dust = data_row
            
            cur.execute(
                """
                UPDATE data_gathered 
                SET pzem_power = %s,
                    pzem_voltage = %s,
                    pzem_current = %s,
                    dht_temp = %s,
                    dht_humidity = %s,
                    ds18b20_temp1 = %s,
                    ds18b20_temp2 = %s,
                    vibration = %s,
                    dust_sensor = %s
                WHERE id = %s
                """,
                (power, voltage, current, outlet_temp, humidity, comp_outlet, inlet_temp, vibration, dust, row_id)
            )

        conn.commit()
        print("Successfully updated all AC4 data in data_gathered!")

    except Exception as e:
        print(f"An error occurred: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    update_ac4()
