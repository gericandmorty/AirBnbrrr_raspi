#!/usr/bin/env python3
import sys
from pathlib import Path

# Add the parent directory of this script to the python path to load database.py
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

try:
    from database import get_db_connection
except ImportError as e:
    print(f"Error importing database: {e}")
    sys.exit(1)

def run_health_analysis():
    print("Connecting to Supabase...")
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM historical_data ORDER BY date")
    rows = cur.fetchall()
    conn.close()

    total_records = len(rows)
    print(f"Retrieved {total_records} historical records.\n")

    # Metrics accumulators
    suction_vals = []
    discharge_vals = []
    water_in_vals = []
    water_out_vals = []
    water_in_press_vals = []
    water_out_press_vals = []
    fan_amp_vals = []
    comp_amp_vals = []
    ac_in_in_vals = []
    ac_in_out_vals = []
    ac_out_vals = []

    off_days_count = 0
    active_days_count = 0
    anomalies = []

    for r in rows:
        # Columns:
        # date, compressor_suction_pressure, compressor_discharge_pressure, water_inlet_temp_c, water_inlet_pressure_mpa,
        # water_outlet_temp_c, water_outlet_pressure_mpa, fan_amperes, compressor_amperes, ac_inlet_temp_in, ac_inlet_temp_out, ac_outlet_temp
        
        date = r["date"]
        suc_p_str = r["compressor_suction_pressure"]
        dis_p_str = r["compressor_discharge_pressure"]
        
        # Check OFF state
        is_off = (suc_p_str == "OFF" or dis_p_str == "OFF")
        if is_off:
            off_days_count += 1
        else:
            active_days_count += 1

        # Safe parsing helpers
        def to_float(val):
            if val is None:
                return None
            try:
                return float(val)
            except ValueError:
                return None

        suc_p = to_float(suc_p_str)
        dis_p = to_float(dis_p_str)
        water_in_t = to_float(r["water_inlet_temp_c"])
        water_in_p = to_float(r["water_inlet_pressure_mpa"])
        water_out_t = to_float(r["water_outlet_temp_c"])
        water_out_p = to_float(r["water_outlet_pressure_mpa"])
        fan_amp = to_float(r["fan_amperes"])
        comp_amp = to_float(r["compressor_amperes"])
        ac_in_in = to_float(r["ac_inlet_temp_in"])
        ac_in_out = to_float(r["ac_inlet_temp_out"])
        ac_out = to_float(r["ac_outlet_temp"])

        # Accumulate numeric values
        if suc_p is not None: suction_vals.append(suc_p)
        if dis_p is not None: discharge_vals.append(dis_p)
        if water_in_t is not None: water_in_vals.append(water_in_t)
        if water_out_t is not None: water_out_vals.append(water_out_t)
        if water_in_p is not None: water_in_press_vals.append(water_in_p)
        if water_out_p is not None: water_out_press_vals.append(water_out_p)
        if fan_amp is not None: fan_amp_vals.append(fan_amp)
        if comp_amp is not None: comp_amp_vals.append(comp_amp)
        if ac_in_in is not None: ac_in_in_vals.append(ac_in_in)
        if ac_in_out is not None: ac_in_out_vals.append(ac_in_out)
        if ac_out is not None: ac_out_vals.append(ac_out)

        # ────────────────────────────────────────────────────────
        # PHYSICAL RULE CHECKS (Per Row)
        # ────────────────────────────────────────────────────────
        
        # Rule 1: High discharge pressure
        if dis_p is not None and dis_p > 2.2:
            anomalies.append({
                "date": date,
                "type": "High Discharge Pressure",
                "message": f"Discharge pressure {dis_p} MPa exceeds safe operating limit (2.2 MPa). Risk of compressor damage.",
                "severity": "High"
            })
            
        # Rule 2: Low pressure difference when compressor is active
        if suc_p is not None and dis_p is not None:
            press_diff = dis_p - suc_p
            if press_diff < 0.3 and not is_off and comp_amp is not None and comp_amp > 5:
                anomalies.append({
                    "date": date,
                    "type": "Low Pressure Differential",
                    "message": f"Pressure difference (Discharge - Suction) is only {press_diff:.2f} MPa (Suction={suc_p} MPa, Discharge={dis_p} MPa) while active. Indicates low compressor efficiency or pump failure.",
                    "severity": "Medium"
                })

        # Rule 3: Zero water temperature difference while compressor draws current
        if water_in_t is not None and water_out_t is not None and not is_off and comp_amp is not None and comp_amp > 10:
            temp_diff = abs(water_out_t - water_in_t)
            if temp_diff < 0.2:
                anomalies.append({
                    "date": date,
                    "type": "Zero Heat Exchange",
                    "message": f"Water Inlet/Outlet temp difference is too low ({temp_diff:.1f}°C) while compressor is active (Current={comp_amp}A, Inlet={water_in_t}°C, Outlet={water_out_t}°C). Indicates water flow blockage or refrigerant cycle failure.",
                    "severity": "High"
                })

        # Rule 4: Overcurrent / Electrical overloading
        if comp_amp is not None and comp_amp > 45:
            anomalies.append({
                "date": date,
                "type": "Overloaded Compressor Current",
                "message": f"Compressor current draw is {comp_amp}A, which exceeds safe operating current (>45A). Risk of winding burn out.",
                "severity": "Critical"
            })
            
        # Rule 5: Zero cooling (AC outlet temp >= AC inlet temp IN when compressor is running)
        if ac_in_in is not None and ac_out is not None and not is_off and comp_amp is not None and comp_amp > 10:
            cooling_diff = ac_in_in - ac_out
            if cooling_diff <= 0:
                anomalies.append({
                    "date": date,
                    "type": "No Cooling Output",
                    "message": f"AC Outlet Temp ({ac_out}°C) is higher than/equal to Inlet Room Temp ({ac_in_in}°C) while compressor is running. The system is not cooling.",
                    "severity": "High"
                })

    # Output stats
    print("=== DATA SUMMARY METRICS ===")
    print(f"Compressor OFF days : {off_days_count} / {total_records}")
    print(f"Compressor Active   : {active_days_count} / {total_records}")
    
    def print_stat(label, vals, unit):
        if vals:
            print(f"  - {label:<22}: Min={min(vals):>5.2f}{unit}, Max={max(vals):>5.2f}{unit}, Mean={sum(vals)/len(vals):>5.2f}{unit}")
        else:
            print(f"  - {label:<22}: N/A")

    print_stat("Suction Pressure", suction_vals, " MPa")
    print_stat("Discharge Pressure", discharge_vals, " MPa")
    print_stat("Water Inlet Temp", water_in_vals, " °C")
    print_stat("Water Outlet Temp", water_out_vals, " °C")
    print_stat("Water Inlet Pressure", water_in_press_vals, " MPa")
    print_stat("Water Outlet Pressure", water_out_press_vals, " MPa")
    print_stat("Fan Current", fan_amp_vals, " A")
    print_stat("Compressor Current", comp_amp_vals, " A")
    print_stat("AC Inlet Temp (IN)", ac_in_in_vals, " °C")
    print_stat("AC Inlet Temp (OUT)", ac_in_out_vals, " °C")
    print_stat("AC Outlet Temp", ac_out_vals, " °C")
    print("\n")

    print("=== HEALTH STATUS & ANOMALIES ===")
    if not anomalies:
        print("✅ SUCCESS: No physical anomalies, overcurrent issues, pressure failures, or heating/cooling inefficiencies detected!")
        print("The historical data is clean and represents a healthy operating profile suitable for training or baseline settings.")
    else:
        print(f"⚠️ WARNING: Found {len(anomalies)} anomalous records in the historical data:")
        critical_count = 0
        high_count = 0
        medium_count = 0
        for anom in anomalies:
            if anom["severity"] == "Critical": critical_count += 1
            elif anom["severity"] == "High": high_count += 1
            else: medium_count += 1
            print(f"  [{anom['severity']}] Date: {anom['date']} | Type: {anom['type']} | {anom['message']}")
        
        print(f"\nSummary: {critical_count} Critical, {high_count} High, {medium_count} Medium issues.")

if __name__ == "__main__":
    run_health_analysis()
