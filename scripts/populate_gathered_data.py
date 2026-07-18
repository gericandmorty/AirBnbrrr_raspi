#!/usr/bin/env python3
import sys
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add the parent directory of this script to the python path to load database.py
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from database import get_db_connection
from psycopg2.extras import execute_values

def jitter(val, min_val, max_val):
    """Generate a value within min_val and max_val using uniform distribution."""
    return round(random.uniform(min_val, max_val), 2)

def generate_telemetry_for_ac(ac_unit, timestamp, pzem_energy):
    """Generate telemetry dictionary for the specified AC unit at the given timestamp."""
    
    # 1. AC3: Compressor Overheating Anomaly (Based on AC2/AC3 baseline but with high ds18b20_temp1)
    if ac_unit == "AC3":
        # Output Temp: ~8.9 °C, Humidity: ~99%, Vibration: ~72.9 Hz, Inlet Temp: ~12.6 °C, Watts: ~1692 W, Amps: ~7.55 A
        # ds18b20_temp1 (discharge temp) overheats to 92-102 °C (normal is 55-90 °C)
        pzem_power = jitter(1692, 1650, 1720)
        pzem_voltage = jitter(228, 226, 230)
        pzem_current = round(pzem_power / pzem_voltage, 3)
        return {
            "ac_unit": "AC3",
            "dust_sensor": None,
            "dht_temp": jitter(8.9, 8.2, 9.6),
            "dht_humidity": jitter(99.0, 97.0, 100.0),
            "vibration": jitter(72.9, 70.0, 75.0),
            "ds18b20_temp1": jitter(97.0, 92.0, 102.0), # Anomaly: Overheating (normal range is 55-90 C)
            "ds18b20_temp2": jitter(12.6, 11.5, 13.5),
            "pzem_voltage": pzem_voltage,
            "pzem_current": pzem_current,
            "pzem_power": pzem_power,
            "pzem_energy": pzem_energy,
            "pzem_frequency": jitter(60.0, 59.8, 60.2),
            "pzem_power_factor": jitter(0.88, 0.85, 0.92),
            "ac_status": "1",
            "ac_thermostat": "22"
        }

    # 2. AC4: Compressor Overheating Anomaly (Based on New Spec baseline but with high ds18b20_temp1)
    elif ac_unit == "AC4":
        # Baseline Watts: 1700-1820, Volts: 225-229, Amps: 7.6-8.2
        # Anomaly: Outlet Compressor Temp ds18b20_temp1 rises to 75-85 °C (normal 56-62 C)
        # and Output Temp dht_temp degrades to 26-28 °C (normal 22-23 C)
        pzem_power = jitter(1850, 1820, 1890) # Slightly high due to compressor strain
        pzem_voltage = jitter(227, 225, 229)
        pzem_current = round(pzem_power / pzem_voltage, 3)
        return {
            "ac_unit": "AC4",
            "dust_sensor": None,
            "dht_temp": jitter(27.0, 26.0, 28.0), # Anomaly: Degraded Output Temp (normal is 22-23 C)
            "dht_humidity": jitter(70.0, 68.0, 72.0),
            "vibration": jitter(75.0, 60.0, 90.0),
            "ds18b20_temp1": jitter(80.0, 75.0, 85.0), # Anomaly: Overheating (normal is 56-62 C)
            "ds18b20_temp2": jitter(9.5, 8.0, 11.0),
            "pzem_voltage": pzem_voltage,
            "pzem_current": pzem_current,
            "pzem_power": pzem_power,
            "pzem_energy": pzem_energy,
            "pzem_frequency": jitter(60.0, 59.8, 60.2),
            "pzem_power_factor": jitter(0.88, 0.85, 0.92),
            "ac_status": "1",
            "ac_thermostat": "22"
        }

    # 3. AC5: Refrigerant Leak Anomaly (Based on New Spec baseline but high ds18b20_temp2, low power)
    elif ac_unit == "AC5":
        # Baseline Watts: 1700-1820, Volts: 225-229, Amps: 7.6-8.2
        # Anomaly: Inlet Compressor Temp ds18b20_temp2 rises to 16-22 °C (normal 8-11 C)
        # and Output Temp dht_temp degrades to 25-27 °C (normal 22-23 C)
        # and Watts drops to 1400-1550 W (Amps drops to 6.2-7.0 A) due to lower load
        pzem_power = jitter(1475, 1400, 1550) # Anomaly: Low Watts (normal is 1700-1820 W)
        pzem_voltage = jitter(227, 225, 229)
        pzem_current = round(pzem_power / pzem_voltage, 3)
        return {
            "ac_unit": "AC5",
            "dust_sensor": None,
            "dht_temp": jitter(26.0, 25.0, 27.0), # Anomaly: Degraded Output Temp
            "dht_humidity": jitter(70.0, 68.0, 72.0),
            "vibration": jitter(75.0, 60.0, 90.0),
            "ds18b20_temp1": jitter(48.5, 45.0, 52.0), # Low discharge temp due to low charge
            "ds18b20_temp2": jitter(19.0, 16.0, 22.0), # Anomaly: High Suction Temp (normal is 8-11 C)
            "pzem_voltage": pzem_voltage,
            "pzem_current": pzem_current,
            "pzem_power": pzem_power,
            "pzem_energy": pzem_energy,
            "pzem_frequency": jitter(60.0, 59.8, 60.2),
            "pzem_power_factor": jitter(0.82, 0.78, 0.85),
            "ac_status": "1",
            "ac_thermostat": "22"
        }

    # 4. AC6: Excessive Vibration Anomaly (Based on New Spec baseline but high vibration)
    elif ac_unit == "AC6":
        # Baseline Watts: 1700-1820, Volts: 225-229, Amps: 7.6-8.2
        # Anomaly: Vibration rises to 110-140 Hz (normal 60-90 Hz)
        pzem_power = jitter(1830, 1800, 1870) # Slightly higher due to motor friction
        pzem_voltage = jitter(227, 225, 229)
        pzem_current = round(pzem_power / pzem_voltage, 3)
        return {
            "ac_unit": "AC6",
            "dust_sensor": None,
            "dht_temp": jitter(22.5, 22.0, 23.0),
            "dht_humidity": jitter(70.0, 69.0, 71.0),
            "vibration": jitter(125.0, 110.0, 140.0), # Anomaly: Excessive vibration (normal is 60-90 Hz)
            "ds18b20_temp1": jitter(59.0, 56.0, 62.0),
            "ds18b20_temp2": jitter(9.5, 8.0, 11.0),
            "pzem_voltage": pzem_voltage,
            "pzem_current": pzem_current,
            "pzem_power": pzem_power,
            "pzem_energy": pzem_energy,
            "pzem_frequency": jitter(60.0, 59.8, 60.2),
            "pzem_power_factor": jitter(0.88, 0.85, 0.92),
            "ac_status": "1",
            "ac_thermostat": "22"
        }

    # 5. AC7: Evaporator Freezing Anomaly (Based on New Spec baseline but low ds18b20_temp2, poor cooling)
    elif ac_unit == "AC7":
        # Baseline Watts: 1700-1820, Volts: 225-229, Amps: 7.6-8.2
        # Anomaly: Inlet Compressor Temp ds18b20_temp2 drops to 1.5-3.5 °C (normal 8-11 C, freezing < 4 C)
        # and Output Temp dht_temp degrades to 24-26 °C (normal 22-23 C) due to iced coil restricting airflow
        pzem_power = jitter(1760, 1720, 1800)
        pzem_voltage = jitter(227, 225, 229)
        pzem_current = round(pzem_power / pzem_voltage, 3)
        return {
            "ac_unit": "AC7",
            "dust_sensor": None,
            "dht_temp": jitter(25.0, 24.0, 26.0), # Anomaly: Degraded Output Temp (due to restricted air)
            "dht_humidity": jitter(78.0, 75.0, 82.0), # Slightly higher humidity
            "vibration": jitter(75.0, 60.0, 90.0),
            "ds18b20_temp1": jitter(57.5, 55.0, 60.0),
            "ds18b20_temp2": jitter(2.5, 1.5, 3.5), # Anomaly: Freezing Suction Line (normal is 8-11 C, frozen < 4 C)
            "pzem_voltage": pzem_voltage,
            "pzem_current": pzem_current,
            "pzem_power": pzem_power,
            "pzem_energy": pzem_energy,
            "pzem_frequency": jitter(60.0, 59.8, 60.2),
            "pzem_power_factor": jitter(0.88, 0.85, 0.92),
            "ac_status": "1",
            "ac_thermostat": "22"
        }

def main():
    print("Connecting to the database...")
    conn = get_db_connection()
    cur = conn.cursor()
    
    print("Fetching AC2 timestamps from July 14...")
    cur.execute("SELECT timestamp FROM data_gathered WHERE ac_unit = 'AC2' ORDER BY timestamp ASC")
    ac2_rows = cur.fetchall()
    
    if not ac2_rows:
        print("ERROR: No AC2 rows found in data_gathered table! Cannot map timestamps.")
        conn.close()
        sys.exit(1)
        
    print(f"Loaded {len(ac2_rows)} timestamps from AC2.")
    
    units = ["AC3", "AC4", "AC5", "AC6", "AC7"]
    days_offsets = [1, 2, 3] # +1 day (July 15), +2 days (July 16), +3 days (July 17)
    
    insert_query = """
    INSERT INTO data_gathered (
        timestamp, ac_unit, dust_sensor, dht_temp, dht_humidity, vibration,
        ds18b20_temp1, ds18b20_temp2, pzem_voltage, pzem_current, pzem_power,
        pzem_energy, pzem_frequency, pzem_power_factor, ac_status, ac_thermostat
    ) VALUES %s
    """
    
    batch_data = []
    
    print("Generating telemetry data with cumulative energy for AC3, AC4, AC5, AC6, AC7...")
    for offset in days_offsets:
        target_date_str = (ac2_rows[0]['timestamp'] + timedelta(days=offset)).strftime("%B %d, %Y")
        print(f"  Generating data for shifted date: {target_date_str}...")
        
        # Initialize running energy in Wh (starting at a realistic baseline 40000.0 Wh)
        running_energy = {u: 40000.0 for u in units}
        prev_timestamp = None
        
        for row in ac2_rows:
            # Shift the timestamp by the specified number of days
            shifted_timestamp = row['timestamp'] + timedelta(days=offset)
            
            # Calculate time difference in hours
            if prev_timestamp is None:
                dt_hours = 0.0
            else:
                dt_hours = (shifted_timestamp - prev_timestamp).total_seconds() / 3600.0
                
            prev_timestamp = shifted_timestamp
            
            for ac_unit in units:
                # Generate telemetry with current cumulative energy
                telemetry = generate_telemetry_for_ac(ac_unit, shifted_timestamp, running_energy[ac_unit])
                
                # Accumulate energy (power * time) for the next step
                power = telemetry["pzem_power"]
                energy_added = power * dt_hours
                running_energy[ac_unit] += energy_added
                
                batch_data.append((
                    shifted_timestamp,
                    telemetry["ac_unit"],
                    telemetry["dust_sensor"],
                    telemetry["dht_temp"],
                    telemetry["dht_humidity"],
                    telemetry["vibration"],
                    telemetry["ds18b20_temp1"],
                    telemetry["ds18b20_temp2"],
                    telemetry["pzem_voltage"],
                    telemetry["pzem_current"],
                    telemetry["pzem_power"],
                    telemetry["pzem_energy"],
                    telemetry["pzem_frequency"],
                    telemetry["pzem_power_factor"],
                    telemetry["ac_status"],
                    telemetry["ac_thermostat"]
                ))
    
    print(f"Inserting {len(batch_data)} records into data_gathered...")
    # Execute batch insertion
    execute_values(cur, insert_query, batch_data)
    conn.commit()
    total_inserted = len(batch_data)
    
    print(f"SUCCESS: Successfully inserted {total_inserted} mock telemetry records!")
    
    # Run a count check per AC unit to verify
    print("\n--- Verifying Row Counts in Database ---")
    cur.execute("SELECT ac_unit, COUNT(*) FROM data_gathered GROUP BY ac_unit ORDER BY ac_unit")
    for r in cur.fetchall():
        print(f"  Unit: {r['ac_unit']} | Count: {r['count']}")
        
    conn.close()
    print("Database connection closed.")

if __name__ == "__main__":
    main()
