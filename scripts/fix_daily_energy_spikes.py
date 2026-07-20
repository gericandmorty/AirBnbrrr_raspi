#!/usr/bin/env python3
import sys
import random
from datetime import datetime, timedelta
from pathlib import Path

# Add the parent directory of this script to the Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from database import get_db_connection
from psycopg2.extras import execute_values

# User-provided 16 telemetry rows for AC4
AC4_NEW_DATA = [
    # Power, Voltage, Current, Outlet Temp, Humidity, Compressor Outlet, Inlet Temp, Vibration, Dust
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

# Base template for AC5 (Refrigerant Leak)
AC5_BASE_TELEMETRY = {
    "dust_sensor": 0.00,
    "dht_temp": 26.0,          # High output temp (> 25 °C)
    "dht_humidity": 70.0,
    "vibration": 75.0,
    "ds18b20_temp1": 48.5,     # Low discharge temp (< 50 °C)
    "ds18b20_temp2": 19.0,     # High suction temp (> 17 °C)
    "pzem_voltage": 227.0,
    "pzem_current": 6.5,       # Low current (< 7.6 A)
    "pzem_power": 1475.0,      # Low power (< 1700 W)
    "pzem_energy": 0.0,
    "pzem_frequency": 60.0,
    "pzem_power_factor": 0.82,
    "ac_status": "1",
    "ac_thermostat": "22"
}

def generate_telemetry_for_ac5(pzem_energy):
    """Generate telemetry with small random variations for AC5 Refrigerant Leak."""
    power = round(random.uniform(1450.0, 1500.0), 1)
    voltage = round(random.uniform(226.0, 228.5), 1)
    current = round(power / voltage, 2)
    return {
        "dust_sensor": 0.00, # Clean air quality as requested
        "dht_temp": round(random.uniform(25.5, 26.5), 1),
        "dht_humidity": round(random.uniform(69.0, 71.0), 1),
        "vibration": round(random.uniform(70.0, 80.0), 1),
        "ds18b20_temp1": round(random.uniform(47.0, 50.0), 1),
        "ds18b20_temp2": round(random.uniform(18.0, 20.0), 1),
        "pzem_voltage": voltage,
        "pzem_current": current,
        "pzem_power": power,
        "pzem_energy": pzem_energy,
        "pzem_frequency": round(random.uniform(59.9, 60.1), 1),
        "pzem_power_factor": round(random.uniform(0.80, 0.84), 2),
        "ac_status": "1",
        "ac_thermostat": "22"
    }

def fix_spikes():
    print("Connecting to the database...")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        return

    try:
        # Load AC2 timestamps (July 7) to shift
        print("Loading baseline timestamps from AC2...")
        cur.execute(
            "SELECT timestamp FROM data_gathered WHERE ac_unit = 'AC2' ORDER BY timestamp ASC"
        )
        ac2_rows = cur.fetchall()

        if not ac2_rows:
            print("ERROR: No AC2 rows found in data_gathered! Can't generate timestamps.")
            return

        print(f"Found {len(ac2_rows)} timestamps.")

        # Clean up existing AC4 and AC5 records
        print("Deleting old duplicate records for AC4 and AC5...")
        cur.execute("DELETE FROM data_gathered WHERE ac_unit IN ('AC4', 'AC5')")

        batch_data = []

        # 1. Regenerate AC4 (July 9, shift = +2 days)
        print("Generating clean, spike-free AC4 telemetry (July 9, 2026)...")
        running_energy_ac4 = 40000.0
        prev_ts_ac4 = None
        for i, row in enumerate(ac2_rows):
            shifted_ts = row['timestamp'] + timedelta(days=2)
            
            if prev_ts_ac4 is not None:
                dt_hours = (shifted_ts - prev_ts_ac4).total_seconds() / 3600.0
            else:
                dt_hours = 0.0
            prev_ts_ac4 = shifted_ts

            data_row = AC4_NEW_DATA[i % len(AC4_NEW_DATA)]
            power, voltage, current, outlet_temp, humidity, comp_outlet, inlet_temp, vibration, dust = data_row
            
            # Increment energy consumption smoothly based on actual power
            running_energy_ac4 += power * dt_hours

            batch_data.append((
                shifted_ts, "AC4", dust, outlet_temp, humidity, vibration,
                comp_outlet, inlet_temp, voltage, current, power,
                running_energy_ac4, 60.0, 0.88, "1", "22"
            ))

        # 2. Regenerate AC5 (July 13, shift = +6 days)
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
        print(f"Successfully generated and inserted {len(batch_data)} records for AC4 and AC5!")

    except Exception as e:
        print(f"An error occurred: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    fix_spikes()
