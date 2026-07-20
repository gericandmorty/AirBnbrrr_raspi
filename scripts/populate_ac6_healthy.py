#!/usr/bin/env python3
import sys
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add the parent directory of this script to the Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from database import get_db_connection
from psycopg2.extras import execute_values

def generate_healthy_ac6(timestamp, pzem_energy):
    """Generate healthy telemetry data for AC6, similar to AC1 and AC2 baseline specs."""
    # Baseline Specs:
    # Watts: 1700–1820 W
    # Voltage: 225–231 V
    # Ampere: 7.6–8.2 A
    # Output Temp: 7-25°C
    # Humidity: 95-100%
    # Outlet Compressor Temp: 50–70 °C
    # Inlet Compressor Temp: 8–17°C
    # Compressor Vibration: 60–90 Hz
    # dust: 0–340 µg/m³
    
    pzem_power = round(random.uniform(1710.0, 1810.0), 1)
    pzem_voltage = round(random.uniform(226.0, 230.0), 1)
    pzem_current = round(pzem_power / pzem_voltage, 2)
    
    return {
        "ac_unit": "AC6",
        "dust_sensor": 0.00,
        "dht_temp": round(random.uniform(11.5, 14.5), 1),
        "dht_humidity": round(random.uniform(96.0, 99.5), 1),
        "vibration": round(random.uniform(65.0, 85.0), 1),
        "ds18b20_temp1": round(random.uniform(55.0, 65.0), 1),
        "ds18b20_temp2": round(random.uniform(9.0, 14.0), 1),
        "pzem_voltage": pzem_voltage,
        "pzem_current": pzem_current,
        "pzem_power": pzem_power,
        "pzem_energy": pzem_energy,
        "pzem_frequency": round(random.uniform(59.9, 60.1), 1),
        "pzem_power_factor": round(random.uniform(0.86, 0.94), 2),
        "ac_status": "1",
        "ac_thermostat": "22"
    }

def populate_ac6():
    print("Connecting to the database...")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        return

    try:
        # Load AC2 timestamps (July 7) to shift by 13 days to July 20
        print("Loading baseline timestamps from AC2...")
        cur.execute(
            "SELECT timestamp FROM data_gathered WHERE ac_unit = 'AC2' ORDER BY timestamp ASC"
        )
        ac2_rows = cur.fetchall()

        if not ac2_rows:
            print("ERROR: No AC2 rows found in data_gathered! Can't generate timestamps.")
            return

        print(f"Found {len(ac2_rows)} timestamps to copy.")

        # Delete any existing AC6 records just in case
        print("Cleaning up any existing AC6 records...")
        cur.execute("DELETE FROM data_gathered WHERE ac_unit = 'AC6'")

        batch_data = []
        running_energy = 40000.0
        prev_timestamp = None

        print("Generating healthy AC6 telemetry (July 20, 2026)...")
        for row in ac2_rows:
            # Shift date by 13 days (July 7 -> July 20)
            shifted_timestamp = row['timestamp'] + timedelta(days=13)

            if prev_timestamp is not None:
                dt_hours = (shifted_timestamp - prev_timestamp).total_seconds() / 3600.0
            else:
                dt_hours = 0.0

            prev_timestamp = shifted_timestamp

            # Update energy consumption (Wh)
            # Power is roughly ~1750W.
            # Increment = Power (W) * time difference (hours)
            power_w = 1750.0
            running_energy += power_w * dt_hours

            data = generate_healthy_ac6(shifted_timestamp, running_energy)
            
            batch_data.append((
                shifted_timestamp,
                data["ac_unit"],
                data["dust_sensor"],
                data["dht_temp"],
                data["dht_humidity"],
                data["vibration"],
                data["ds18b20_temp1"],
                data["ds18b20_temp2"],
                data["pzem_voltage"],
                data["pzem_current"],
                data["pzem_power"],
                data["pzem_energy"],
                data["pzem_frequency"],
                data["pzem_power_factor"],
                data["ac_status"],
                data["ac_thermostat"]
            ))

        # Perform fast batch insert
        insert_query = """
        INSERT INTO data_gathered (
            timestamp, ac_unit, dust_sensor, dht_temp, dht_humidity, vibration,
            ds18b20_temp1, ds18b20_temp2, pzem_voltage, pzem_current, pzem_power,
            pzem_energy, pzem_frequency, pzem_power_factor, ac_status, ac_thermostat
        ) VALUES %s
        """
        execute_values(cur, insert_query, batch_data)
        conn.commit()
        print(f"Successfully generated and inserted {len(batch_data)} healthy records for AC6!")

    except Exception as e:
        print(f"An error occurred: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    populate_ac6()
