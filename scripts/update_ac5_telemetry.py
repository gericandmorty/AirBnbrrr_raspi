#!/usr/bin/env python3
import sys
import random
from datetime import datetime, timedelta
from pathlib import Path

# Add the parent directory of this script to the Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from database import get_db_connection
from psycopg2.extras import execute_values

def generate_telemetry_for_ac5(pzem_energy):
    """
    Reduced Cooling Performance signature for AC5:
    - Output air temp (dht_temp): warm but not extreme ~18–22 °C
    - Inlet Compressor (ds18b20_temp2): almost same as output air, but 2–3 °C higher
    - Outlet Compressor (ds18b20_temp1): independently 62–71 °C
    - Dust sensor: 0–200 µg/m³
    - Power, voltage, current all within normal range
    """
    # Output air temp: slightly warm (reduced cooling)
    output_temp = round(random.uniform(18.0, 22.0), 1)
    # Inlet compressor: 2–3 °C above the output air (close but slightly higher)
    delta = round(random.uniform(2.0, 3.0), 1)
    inlet_comp = round(output_temp + delta, 1)

    # Outlet compressor: independently 62–71 °C
    outlet_comp = round(random.uniform(62.0, 71.0), 1)

    power   = round(random.uniform(1650.0, 1860.0), 1)   # Normal
    voltage = round(random.uniform(225.0, 231.0), 1)      # Normal
    current = round(power / voltage, 2)                   # Derived, stays 7.6–8.8 A

    # Dust: 0–200 µg/m³ (10% chance of exactly 0)
    if random.random() < 0.10:
        dust = 0.00
    else:
        dust = round(random.uniform(1.0, 200.0), 2)

    return {
        "dust_sensor":       dust,
        "dht_temp":          output_temp,                              # Output air temp
        "dht_humidity":      round(random.uniform(70.0, 78.0), 1),    # Normal (≤ 80%)
        "vibration":         round(random.uniform(60.0, 85.0), 1),    # Normal (< 90 Hz)
        "ds18b20_temp1":     outlet_comp,                              # Outlet compressor: 62–71 °C
        "ds18b20_temp2":     inlet_comp,                               # Inlet compressor: output + 2–3 °C
        "pzem_voltage":      voltage,
        "pzem_current":      current,
        "pzem_power":        power,
        "pzem_energy":       pzem_energy,
        "pzem_frequency":    round(random.uniform(59.9, 60.1), 1),
        "pzem_power_factor": round(random.uniform(0.86, 0.94), 2),
        "ac_status":         "1",
        "ac_thermostat":     "22"
    }

def update_ac5():
    print("Connecting to the database...")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        return

    try:
        # Load AC2 timestamps (July 7) to shift by 6 days to July 13
        print("Loading baseline timestamps from AC2...")
        cur.execute(
            "SELECT timestamp FROM data_gathered WHERE ac_unit = 'AC2' ORDER BY timestamp ASC"
        )
        ac2_rows = cur.fetchall()

        if not ac2_rows:
            print("ERROR: No AC2 rows found in data_gathered! Can't generate timestamps.")
            return

        print(f"Found {len(ac2_rows)} timestamps.")

        # Clean up existing AC5 records
        print("Deleting old AC5 records...")
        cur.execute("DELETE FROM data_gathered WHERE ac_unit = 'AC5'")

        batch_data = []

        print("Generating clean, spike-free AC5 telemetry (July 13, 2026)...")
        running_energy_ac5 = 40000.0
        prev_ts_ac5 = None
        for i, row in enumerate(ac2_rows):
            shifted_ts = row['timestamp'] + timedelta(days=6)
            
            if prev_ts_ac5 is not None:
                dt_hours = (shifted_ts - prev_ts_ac5).total_seconds() / 3600.0
            else:
                dt_hours = 0.0
            prev_ts_ac5 = shifted_ts

            data = generate_telemetry_for_ac5(running_energy_ac5)
            # Increment energy consumption smoothly based on actual power
            running_energy_ac5 += data["pzem_power"] * dt_hours

            batch_data.append((
                shifted_ts, "AC5", data["dust_sensor"], data["dht_temp"], data["dht_humidity"], data["vibration"],
                data["ds18b20_temp1"], data["ds18b20_temp2"], data["pzem_voltage"], data["pzem_current"], data["pzem_power"],
                running_energy_ac5, data["pzem_frequency"], data["pzem_power_factor"], data["ac_status"], data["ac_thermostat"]
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
        print(f"Successfully generated and inserted {len(batch_data)} records for AC5!")

    except Exception as e:
        print(f"An error occurred: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    update_ac5()
