import sys
from pathlib import Path
import pandas as pd

# Add parent directory to sys.path to import database
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from database import get_db_connection

def analyze_health():
    conn = get_db_connection()
    df = pd.read_sql("SELECT * FROM historical_data ORDER BY date", conn)
    conn.close()

    print(f"Total records in historical_data: {len(df)}")
    
    # Cast numeric columns to float
    num_cols = [
        'water_inlet_temp_c', 'water_inlet_pressure_mpa', 'water_outlet_temp_c', 
        'water_outlet_pressure_mpa', 'fan_amperes', 'compressor_amperes', 
        'ac_inlet_temp_in', 'ac_inlet_temp_out', 'ac_outlet_temp'
    ]
    for col in num_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df['suction_num'] = pd.to_numeric(df['compressor_suction_pressure'], errors='coerce')
    df['discharge_num'] = pd.to_numeric(df['compressor_discharge_pressure'], errors='coerce')

    print("\n--- Summary Stats ---")
    print(f"Compressor Suction Pressure (MPa): Min={df['suction_num'].min()}, Max={df['suction_num'].max()}, Mean={df['suction_num'].mean():.2f}")
    print(f"Compressor Discharge Pressure (MPa): Min={df['discharge_num'].min()}, Max={df['discharge_num'].max()}, Mean={df['discharge_num'].mean():.2f}")
    print(f"Water Inlet Temp (C): Min={df['water_inlet_temp_c'].min()}, Max={df['water_inlet_temp_c'].max()}, Mean={df['water_inlet_temp_c'].mean():.2f}")
    print(f"Water Outlet Temp (C): Min={df['water_outlet_temp_c'].min()}, Max={df['water_outlet_temp_c'].max()}, Mean={df['water_outlet_temp_c'].mean():.2f}")
    print(f"Compressor Amperes (A): Min={df['compressor_amperes'].min()}, Max={df['compressor_amperes'].max()}, Mean={df['compressor_amperes'].mean():.2f}")
    print(f"AC Inlet Temp IN (C): Min={df['ac_inlet_temp_in'].min()}, Max={df['ac_inlet_temp_in'].max()}, Mean={df['ac_inlet_temp_in'].mean():.2f}")
    print(f"AC Inlet Temp OUT (C): Min={df['ac_inlet_temp_out'].min()}, Max={df['ac_inlet_temp_out'].max()}, Mean={df['ac_inlet_temp_out'].mean():.2f}")
    print(f"AC Outlet Temp (C): Min={df['ac_outlet_temp'].min()}, Max={df['ac_outlet_temp'].max()}, Mean={df['ac_outlet_temp'].mean():.2f}")

    # Check compressor OFF states
    off_count = (df['compressor_suction_pressure'] == 'OFF').sum()
    print(f"\nCompressor OFF days: {off_count}")

    # Anomalies checks
    print("\n--- Health Anomalies Detected ---")
    anomalies = []

    # 1. Check for extreme water temperatures
    temp_anoms = df[(df['water_inlet_temp_c'] < 10) | (df['water_outlet_temp_c'] < 10) | (df['water_inlet_temp_c'] > 50) | (df['water_outlet_temp_c'] > 50)]
    for idx, row in temp_anoms.iterrows():
        anomalies.append(f"[{row['date']}] Extreme Water Temperature: Inlet={row['water_inlet_temp_c']}C, Outlet={row['water_outlet_temp_c']}C")

    # 2. Check for negative heat exchange (water outlet temp is lower than or equal to inlet temp when compressor is running)
    active_df = df[df['suction_num'].notna() & (df['compressor_amperes'] > 0)].copy()
    active_df['temp_diff'] = active_df['water_outlet_temp_c'] - active_df['water_inlet_temp_c']
    neg_diff = active_df[active_df['temp_diff'] <= 0]
    for idx, row in neg_diff.iterrows():
        anomalies.append(f"[{row['date']}] Inefficient Heat Exchange (Water Outlet Temp <= Inlet Temp): Inlet={row['water_inlet_temp_c']}C, Outlet={row['water_outlet_temp_c']}C, Diff={row['temp_diff']}C, Compressor Current={row['compressor_amperes']}A")

    # 3. Check for low pressure differential when compressor is active
    active_df['press_diff'] = active_df['discharge_num'] - active_df['suction_num']
    low_press_diff = active_df[active_df['press_diff'] < 0.5]
    for idx, row in low_press_diff.iterrows():
        anomalies.append(f"[{row['date']}] Low Pressure Differential (Discharge - Suction < 0.5 MPa): Suction={row['compressor_suction_pressure']} MPa, Discharge={row['compressor_discharge_pressure']} MPa, Diff={row['press_diff']:.2f} MPa")

    # 4. Check for overloaded compressor current
    high_current = df[df['compressor_amperes'] > 45]
    for idx, row in high_current.iterrows():
        anomalies.append(f"[{row['date']}] Overloaded Compressor Current: {row['compressor_amperes']} A (normal is typically < 40 A for 0.6 HP under normal load)")

    # 5. Check for ineffective cooling (AC outlet temp is higher than inlet in cooling mode)
    cooling_active = df[(df['compressor_amperes'] > 0) & (df['ac_outlet_temp'].notna()) & (df['ac_inlet_temp_in'].notna())].copy()
    cooling_active['ac_temp_diff'] = cooling_active['ac_inlet_temp_in'] - cooling_active['ac_outlet_temp']
    poor_cooling = cooling_active[cooling_active['ac_temp_diff'] <= 0]
    for idx, row in poor_cooling.iterrows():
        anomalies.append(f"[{row['date']}] Poor Cooling (AC Outlet Temp >= Inlet Temp): Inlet IN={row['ac_inlet_temp_in']}C, Outlet={row['ac_outlet_temp']}C, Diff={row['ac_temp_diff']}C")

    # 6. Check for extremely low AC Outlet temperatures (freezing)
    freezing_outlet = df[df['ac_outlet_temp'] < 10]
    for idx, row in freezing_outlet.iterrows():
        anomalies.append(f"[{row['date']}] Extremely Low AC Outlet Temp (Freezing Risk): {row['ac_outlet_temp']}C")

    if not anomalies:
        print("No severe physical anomalies found. The AC/chiller system appears healthy across all operating days!")
    else:
        print(f"Found {len(anomalies)} anomalies/warnings:")
        for anom in anomalies:
            print(f"  - {anom}")

if __name__ == "__main__":
    analyze_health()
