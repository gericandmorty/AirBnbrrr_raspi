import time
from database import get_db_connection

def monitor():
    print("Connecting to database...")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return

    print("Successfully connected. Fetching latest telemetry ID...")
    cur.execute("SELECT id FROM telemetry ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    
    last_id = row['id'] if row else 0
    print(f"Monitoring started. Waiting for new telemetry data (Last seen ID: {last_id})...\n")

    try:
        while True:
            # Query for any new entries
            cur.execute(
                "SELECT id, timestamp, dust_sensor, dht_temp, dht_humidity, ds18b20_temp1, ds18b20_temp2, pzem_voltage, pzem_power "
                "FROM telemetry WHERE id > %s ORDER BY id ASC",
                (last_id,)
            )
            rows = cur.fetchall()
            
            for r in rows:
                last_id = r['id']
                print("-" * 60)
                print(f"NEW DATA RECEIVED! [ID: {r['id']} | Time: {r['timestamp']}]")
                print(f"  - Dust Sensor:       {r['dust_sensor']}")
                print(f"  - DHT Temp/Humidity: {r['dht_temp']}°C / {r['dht_humidity']}%")
                print(f"  - DS18B20 Temp 1/2:  {r['ds18b20_temp1']}°C / {r['ds18b20_temp2']}°C")
                print(f"  - Power (V / W):     {r['pzem_voltage']}V / {r['pzem_power']}W")
                print("-" * 60)
            
            conn.commit() # Clear transaction state
            time.sleep(2)
            
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    monitor()
