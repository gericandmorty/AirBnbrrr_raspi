#!/usr/bin/env python3
"""Seed telemetry.db with sample telemetry rows (at least 10).

Run: python3 scripts/seed_telemetry.py
"""
from pathlib import Path
import sqlite3
import random

DB_PATH = Path("telemetry.db")


def ensure_table(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            dust_sensor REAL,
            dht_temp REAL,
            dht_humidity REAL,
            vibration REAL,
            ds18b20_temp1 REAL,
            ds18b20_temp2 REAL,
            pzem_voltage REAL,
            pzem_current REAL,
            pzem_power REAL,
            pzem_energy REAL,
            pzem_frequency REAL,
            pzem_power_factor REAL,
            ac_status TEXT,
            ac_thermostat TEXT
        )
        """
    )
    conn.commit()


def random_sample(i: int):
    # Generate plausible random samples; omit AC fields for some rows
    sample = {
        "dust_sensor": round(random.uniform(0.0, 1.0), 3),
        "dht_temp": round(random.uniform(15.0, 35.0), 2),
        "dht_humidity": round(random.uniform(20.0, 90.0), 2),
        "vibration": round(random.uniform(60.0, 90.0), 2) if i % 3 != 0 else 0.0,
        "ds18b20_temp1": round(random.uniform(10.0, 40.0), 2),
        "ds18b20_temp2": round(random.uniform(10.0, 40.0), 2),
        "pzem_voltage": round(random.uniform(110.0, 240.0), 2),
        "pzem_current": round(random.uniform(0.0, 30.0), 3),
        "pzem_power": round(random.uniform(0.0, 5000.0), 2),
        "pzem_energy": round(random.uniform(0.0, 10000.0), 2),
        "pzem_frequency": round(random.uniform(45.0, 65.0), 2),
        "pzem_power_factor": round(random.uniform(0.5, 1.0), 3),
    }

    # For some rows, leave AC fields as None to simulate "Not Set" from API
    if i % 3 == 0:
        sample["ac_status"] = 0
        sample["ac_thermostat"] = 0
    else:
        sample["ac_status"] = int(random.uniform(1, 6))
        sample["ac_thermostat"] = int(random.uniform(1, 10))

    return sample


def insert_samples(n: int = 10) -> int:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_table(conn)
    cur = conn.cursor()

    insert_sql = (
        """
        INSERT INTO telemetry (
            dust_sensor, dht_temp, dht_humidity, vibration,
            ds18b20_temp1, ds18b20_temp2,
            pzem_voltage, pzem_current, pzem_power, pzem_energy,
            pzem_frequency, pzem_power_factor,
            ac_status, ac_thermostat
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
    )

    for i in range(1, n + 1):
        s = random_sample(i)
        params = (
            s["dust_sensor"],
            s["dht_temp"],
            s["dht_humidity"],
            s["vibration"],
            s["ds18b20_temp1"],
            s["ds18b20_temp2"],
            s["pzem_voltage"],
            s["pzem_current"],
            s["pzem_power"],
            s["pzem_energy"],
            s["pzem_frequency"],
            s["pzem_power_factor"],
            s["ac_status"],
            s["ac_thermostat"],
        )
        cur.execute(insert_sql, params)

    conn.commit()
    inserted = n
    conn.close()
    return inserted


if __name__ == "__main__":
    COUNT = 10
    inserted = insert_samples(COUNT)
    print(f"Inserted {inserted} sample telemetry rows into {DB_PATH}")
