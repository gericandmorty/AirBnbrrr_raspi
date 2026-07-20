"""
Rule-Based Anomaly Detection Engine for AirBnBrrr
===================================================
A deterministic, physics-based algorithm that checks sensor readings
against hard-coded thresholds derived from the AC unit specifications.

AC Unit Specifications (reference for all thresholds):
  - Capacity     : 1.5 HP
  - Type         : Manual Window Type (Non-Inverter)
  - Refrigerant  : R410A
  - Power Range  : 1700W – 1820W at full cooling
  - Voltage      : 225V – 229V / 60 Hz / 1-Phase
"""

from typing import Optional


# ─────────────────────────────────────────────────────────────
# THRESHOLD DEFINITIONS
# Each entry is:  (sensor_key, min, max, low_issue, high_issue)
# None = no lower / upper bound check for that side
# ─────────────────────────────────────────────────────────────

RULES = [
    # ── POWER (W) ──────────────────────────────────────────────
    {
        "sensor":      "pzem_power",
        "label":       "Power Consumption (W)",
        "unit":        "W",
        "normal_min":  1700.0,
        "normal_max":  1820.0,
        "checks": [
            {
                "condition": lambda v: v > 1820.0,
                "computed":  lambda v: f"{v:.1f} W  >  1820 W threshold",
                "issue":     "Overloaded Compressor or Failing Run Capacitor",
                "severity":  "High",
                "status":    "Current",
                "root_cause": (
                    "Power draw exceeds the rated maximum of 1820 W. "
                    "This indicates the compressor is working harder than normal — "
                    "typically caused by a dirty condenser coil restricting heat dissipation, "
                    "low refrigerant forcing the compressor to cycle longer, "
                    "or a degrading run capacitor reducing motor efficiency."
                ),
                "recommended_action": (
                    "1. Clean the condenser coil and air filter. "
                    "2. Inspect the run capacitor (measure μF, replace if ±10% off). "
                    "3. Have a technician check refrigerant charge."
                ),
            },
            {
                "condition": lambda v: 0 < v < 1700.0,
                "computed":  lambda v: f"{v:.1f} W  <  1700 W threshold",
                "issue":     "Compressor Failed to Start (Fan-Only Mode Suspected)",
                "severity":  "High",
                "status":    "Current",
                "root_cause": (
                    "Power draw is significantly below 1700 W but above 0 W, "
                    "which means only the fan motor (≈50–80 W) is running. "
                    "The compressor did not start. Common causes: failed start capacitor, "
                    "stuck contactor, open compressor winding, or incorrect thermostat mode."
                ),
                "recommended_action": (
                    "1. Check thermostat setting — ensure it is in COOL mode, not FAN-ONLY. "
                    "2. Test the start/run capacitor. "
                    "3. Inspect compressor contactor for wear or welding. "
                    "4. Measure compressor winding continuity."
                ),
            },
            {
                "condition": lambda v: v == 0.0,
                "computed":  lambda v: "0 W — unit appears fully off",
                "issue":     "No Power Draw Detected",
                "severity":  "Critical",
                "status":    "Current",
                "root_cause": (
                    "No electrical power is being consumed. "
                    "The unit may be unplugged, the circuit breaker tripped, "
                    "or the power monitoring sensor itself has failed."
                ),
                "recommended_action": (
                    "1. Verify the unit is powered on at the main switch. "
                    "2. Check the circuit breaker for the AC circuit. "
                    "3. Inspect the PZEM sensor connection."
                ),
            },
        ],
    },

    # ── VOLTAGE (V) ────────────────────────────────────────────
    {
        "sensor":      "pzem_voltage",
        "label":       "Supply Voltage (V)",
        "unit":        "V",
        "normal_min":  225.0,
        "normal_max":  231.0,
        "checks": [
            {
                "condition": lambda v: v < 225.0,
                "computed":  lambda v: f"{v:.1f} V  <  225 V threshold",
                "issue":     "Undervoltage — Risk of Motor Overheating",
                "severity":  "Medium",
                "status":    "Current",
                "root_cause": (
                    "Supply voltage is below the safe operating minimum of 225 V. "
                    "Low voltage forces the compressor motor to draw higher current "
                    "to maintain torque, causing excess heat and accelerating winding degradation."
                ),
                "recommended_action": (
                    "1. Report the low voltage to your electrical utility. "
                    "2. Consider installing a voltage stabilizer/AVR. "
                    "3. Avoid running the AC unit until voltage stabilizes above 225 V."
                ),
            },
            {
                "condition": lambda v: v > 231.0,
                "computed":  lambda v: f"{v:.1f} V  >  231 V threshold",
                "issue":     "Overvoltage — Risk of Component Damage",
                "severity":  "Medium",
                "status":    "Current",
                "root_cause": (
                    "Supply voltage exceeds 231 V. High voltage stresses capacitors, "
                    "control PCBs, and motor windings, significantly shortening their service life."
                ),
                "recommended_action": (
                    "1. Consult your electrical utility about the high voltage. "
                    "2. Install a surge protector or voltage regulator. "
                    "3. Monitor capacitor condition more frequently."
                ),
            },
        ],
    },

    # ── Grid Current / AMPERE (A) ──────────────────────────────
    {
        "sensor":      "pzem_current",
        "label":       "AC Operating Current (A)",
        "unit":        "A",
        "normal_min":  7.6,
        "normal_max":  8.2,
        "checks": [
            {
                "condition": lambda v: v > 8.2,
                "computed":  lambda v: f"{v:.2f} A  >  8.2 A threshold",
                "issue":     "High AC Current — Overloaded Compressor Winding",
                "severity":  "High",
                "status":    "Current",
                "root_cause": (
                    "Current draw exceeds 8.2 A. This indicates the compressor motor "
                    "is under high mechanical load, operating with a weak run capacitor, "
                    "or experiencing elevated high-side refrigerant pressures."
                ),
                "recommended_action": (
                    "1. Check the condenser coil for blockages and clean it. "
                    "2. Verify run capacitor capacitance. "
                    "3. Have a technician inspect refrigerant pressures."
                ),
            },
            {
                "condition": lambda v: 0.1 < v < 7.6,
                "computed":  lambda v: f"{v:.2f} A  <  7.6 A threshold",
                "issue":     "Low AC Current — Compressor Underload or Failure to Start",
                "severity":  "High",
                "status":    "Current",
                "root_cause": (
                    "Current draw is below 7.6 A while the unit is supposedly running. "
                    "This suggests the compressor failed to start (only the fan is drawing power) "
                    "or is running completely underloaded due to a total loss of refrigerant."
                ),
                "recommended_action": (
                    "1. Confirm if the compressor is active and blowing warm air from condenser. "
                    "2. Check thermostat and start components. "
                    "3. Inspect for refrigerant leaks."
                ),
            },
        ],
    },

    # ── OUTPUT TEMP / DHT TEMP (°C) ─────────────────────────────
    {
        "sensor":      "dht_temp",
        "label":       "AC Output Temperature (°C)",
        "unit":        "°C",
        "normal_min":  7.0,
        "normal_max":  25.0,
        "checks": [
            {
                "condition": lambda v: v > 25.0,
                "computed":  lambda v: f"{v:.1f} °C  >  25.0 °C threshold",
                "issue":     "Poor Cooling Output — High Supply Temp",
                "severity":  "High",
                "status":    "Current",
                "root_cause": (
                    "AC output air temperature is warmer than 25 °C. This suggests "
                    "reduced cooling performance due to a dirty evaporator filter, "
                    "refrigerant loss, or restricted airflow."
                ),
                "recommended_action": (
                    "1. Clean or replace the front air filter. "
                    "2. Check if the compressor is running. "
                    "3. Have a technician verify system pressures."
                ),
            },
            {
                "condition": lambda v: v < 7.0 and v > 0,
                "computed":  lambda v: f"{v:.1f} °C  <  7.0 °C threshold",
                "issue":     "Low Output Temp — Overcooling or Freezing Risk",
                "severity":  "Medium",
                "status":    "Current",
                "root_cause": (
                    "AC output temperature is below 7 °C, which is colder than expected. "
                    "This can lead to evaporator coil icing if return air is restricted."
                ),
                "recommended_action": (
                    "1. Verify return air filter is clean. "
                    "2. Ensure fan speed is set properly and not restricted."
                ),
            },
        ],
    },

    # ── HUMIDITY / DHT HUMIDITY (%) ──────────────────────────────
    {
        "sensor":      "dht_humidity",
        "label":       "AC Output Humidity (%)",
        "unit":        "%",
        "normal_min":  95.0,
        "normal_max":  100.0,
        "checks": [
            {
                "condition": lambda v: v < 95.0,
                "computed":  lambda v: f"{v:.1f}%  <  95% threshold",
                "issue":     "Low Output Humidity — Inefficient Dehumidification",
                "severity":  "Medium",
                "status":    "Current",
                "root_cause": (
                    "Humidity level of the supply air is below 95%."
                ),
                "recommended_action": (
                    "1. Verify the thermostat setpoint and clean the evaporator coil."
                ),
            },
        ],
    },

    # ── FREQUENCY (Hz) ─────────────────────────────────────────
    {
        "sensor":      "pzem_frequency",
        "label":       "Grid Frequency (Hz)",
        "unit":        "Hz",
        "normal_min":  59.0,
        "normal_max":  61.0,
        "checks": [
            {
                "condition": lambda v: v < 59.0 or v > 61.0,
                "computed":  lambda v: f"{v:.1f} Hz  outside 59–61 Hz range",
                "issue":     "Grid Frequency Instability",
                "severity":  "Low",
                "status":    "Current",
                "root_cause": (
                    "Mains frequency is outside the normal 60 Hz ±1 Hz tolerance. "
                    "Frequency deviation affects induction motor speed and can cause "
                    "compressor and fan motor efficiency loss."
                ),
                "recommended_action": (
                    "1. Monitor frequency over time — short transients are usually harmless. "
                    "2. If sustained, report to the electrical utility. "
                    "3. For critical installations, consider a UPS or frequency conditioner."
                ),
            },
        ],
    },

    # ── POWER FACTOR ───────────────────────────────────────────
    {
        "sensor":      "pzem_power_factor",
        "label":       "Power Factor",
        "unit":        "",
        "normal_min":  0.85,
        "normal_max":  1.00,
        "checks": [
            {
                "condition": lambda v: v < 0.85,
                "computed":  lambda v: f"PF = {v:.2f}  <  0.85 threshold",
                "issue":     "Low Power Factor — Possible Capacitor Degradation",
                "severity":  "Medium",
                "status":    "Predicted",
                "root_cause": (
                    "Power factor below 0.85 indicates the motor is drawing excessive "
                    "reactive current relative to real power. In non-inverter AC units, "
                    "this is a strong indicator that the run capacitor is losing capacitance."
                ),
                "recommended_action": (
                    "1. Measure the run capacitor with a capacitance meter. "
                    "2. Replace if reading is more than 10% below rated value. "
                    "3. A degraded capacitor also reduces cooling capacity and increases wear."
                ),
            },
        ],
    },

    # ── DISCHARGE LINE TEMPERATURE / OUTLET COMPRESSOR TEMP (ds18b20_temp1) ──
    {
        "sensor":      "ds18b20_temp1",
        "label":       "Discharge Line Temperature (°C)",
        "unit":        "°C",
        "normal_min":  50.0,
        "normal_max":  70.0,
        "checks": [
            {
                "condition": lambda v: v > 70.0,
                "computed":  lambda v: f"{v:.1f} °C  >  70 °C threshold",
                "issue":     "High Discharge Temp — Dirty Condenser or Low Refrigerant",
                "severity":  "High",
                "status":    "Current",
                "root_cause": (
                    "Compressor discharge line temperature exceeds 70 °C. "
                    "High discharge temps indicate either: (1) the condenser coil is dirty "
                    "and cannot reject heat efficiently, or (2) refrigerant charge is low, "
                    "causing the refrigeration cycle to work harder."
                ),
                "recommended_action": (
                    "1. Clean the condenser coil (outdoor side) with a fin comb or hose. "
                    "2. Check for blocked airflow around the unit. "
                    "3. Have a certified technician check refrigerant pressure and recharge if needed."
                ),
            },
            {
                "condition": lambda v: v < 50.0 and v > 0,
                "computed":  lambda v: f"{v:.1f} °C  <  50 °C threshold",
                "issue":     "Low Discharge Temp — Possible Refrigerant Undercharge",
                "severity":  "Medium",
                "status":    "Current",
                "root_cause": (
                    "Discharge temperature is unusually low. If the compressor is running, "
                    "this may indicate a refrigerant undercharge where the system is "
                    "not building up sufficient head pressure."
                ),
                "recommended_action": (
                    "1. Have a technician verify refrigerant pressure with manifold gauges. "
                    "2. Inspect for refrigerant leaks at fittings and the evaporator coil."
                ),
            },
        ],
    },

    # ── SUCTION LINE TEMPERATURE / INLET COMPRESSOR TEMP (ds18b20_temp2) ─────
    {
        "sensor":      "ds18b20_temp2",
        "label":       "Suction Line Temperature (°C)",
        "unit":        "°C",
        "normal_min":  8.0,
        "normal_max":  17.0,
        "checks": [
            {
                "condition": lambda v: v < 8.0 and v > -10,
                "computed":  lambda v: f"{v:.1f} °C  <  8 °C threshold",
                "issue":     "Low Suction Temp — Evaporator Freezing Risk",
                "severity":  "High",
                "status":    "Current",
                "root_cause": (
                    "Suction line temperature below 8 °C indicates the evaporator "
                    "coil is icing up. Causes: (1) severely dirty air filter restricting airflow, "
                    "(2) dirty evaporator coil, or (3) low refrigerant charge."
                ),
                "recommended_action": (
                    "1. Turn off the AC immediately — running with a frozen coil damages the compressor. "
                    "2. Let the ice melt, then clean the air filter. "
                    "3. If freezing recurs, have a technician inspect the refrigerant charge."
                ),
            },
            {
                "condition": lambda v: v > 17.0,
                "computed":  lambda v: f"{v:.1f} °C  >  17 °C threshold",
                "issue":     "High Suction Temp — Insufficient Cooling / Refrigerant Loss",
                "severity":  "Medium",
                "status":    "Current",
                "root_cause": (
                    "Suction line temperature above 17 °C indicates the refrigerant "
                    "is absorbing too little heat — often a sign of refrigerant loss, "
                    "very high room temperature, or a partially blocked metering device."
                ),
                "recommended_action": (
                    "1. Check ambient temperature — above 35 °C room temps stress any AC unit. "
                    "2. Have refrigerant pressure checked. "
                    "3. Inspect the filter/expansion valve if accessible."
                ),
            },
        ],
    },

    # ── VIBRATION (Hz) ─────────────────────────────────────────
    {
        "sensor":      "vibration",
        "label":       "Compressor Vibration (Hz)",
        "unit":        "Hz",
        "normal_min":  60.0,
        "normal_max":  90.0,
        "checks": [
            {
                "condition": lambda v: v > 90.0,
                "computed":  lambda v: f"{v:.1f} Hz  >  90 Hz threshold",
                "issue":     "Excessive Compressor Vibration — Mechanical Wear or Loose Mount",
                "severity":  "Medium",
                "status":    "Current",
                "root_cause": (
                    "Compressor vibration above 90 Hz is abnormal. "
                    "Possible causes: worn compressor internal components, "
                    "loose mounting bolts, or deteriorated rubber anti-vibration grommets."
                ),
                "recommended_action": (
                    "1. Tighten all visible compressor mounting bolts. "
                    "2. Inspect and replace anti-vibration grommets if hardened or cracked. "
                    "3. If vibration continues, have the compressor inspected for internal wear."
                ),
            },
        ],
    },

    # ── DUST SENSOR ────────────────────────────────────────────
    {
        "sensor":      "dust_sensor",
        "label":       "Dust Level",
        "unit":        "µg/m³",
        "normal_min":  0.0,
        "normal_max":  340.0,
        "checks": [
            {
                "condition": lambda v: v > 340.0,
                "computed":  lambda v: f"{v:.1f} µg/m³  >  340 µg/m³ threshold",
                "issue":     "Dirty Air Filter — Restricted Airflow",
                "severity":  "Low",
                "status":    "Current",
                "root_cause": (
                    "The dust sensor behind the front filter reads above 340 µg/m³, "
                    "indicating a dirty filter that restricts return airflow. "
                    "Reduced airflow leads to a warmer evaporator coil, lower cooling capacity, "
                    "and over time, compressor overwork."
                ),
                "recommended_action": (
                    "1. Remove and clean (or replace) the front air filter. "
                    "2. Schedule filter cleaning every 2–4 weeks in dusty environments. "
                    "3. After cleaning, monitor if other sensor readings normalize."
                ),
            },
        ],
    },

    # ── COMPRESSOR SUCTION PRESSURE ──────────────────────────────
    {
        "sensor":      "compressor_suction_pressure",
        "label":       "Compressor Suction Pressure (MPa)",
        "unit":        "MPa",
        "normal_min":  0.30,
        "normal_max":  0.60,
        "checks": [
            {
                "condition": lambda v: v > 0.60,
                "computed":  lambda v: f"{v:.2f} MPa > 0.60 MPa threshold",
                "issue":     "High Compressor Suction Pressure",
                "severity":  "Medium",
                "status":    "Current",
                "root_cause": (
                    "High suction pressure indicates high heat load on the evaporator "
                    "or an inefficient compressor (leaking valves/seals)."
                ),
                "recommended_action": (
                    "1. Inspect return air filter and evaporator fan. "
                    "2. Have a technician check compressor valve efficiency."
                )
            },
            {
                "condition": lambda v: v < 0.30,
                "computed":  lambda v: f"{v:.2f} MPa < 0.30 MPa threshold",
                "issue":     "Low Compressor Suction Pressure",
                "severity":  "High",
                "status":    "Current",
                "root_cause": (
                    "Low suction pressure indicates low refrigerant charge or restricted "
                    "suction line/airflow over the evaporator (coil freezing)."
                ),
                "recommended_action": (
                    "1. Check refrigerant charge. 2. Verify expansion valve/metering device flow. "
                    "3. Inspect evaporator coil for frost/ice."
                )
            }
        ]
    },

    # ── COMPRESSOR DISCHARGE PRESSURE ────────────────────────────
    {
        "sensor":      "compressor_discharge_pressure",
        "label":       "Compressor Discharge Pressure (MPa)",
        "unit":        "MPa",
        "normal_min":  1.40,
        "normal_max":  2.20,
        "checks": [
            {
                "condition": lambda v: v > 2.20,
                "computed":  lambda v: f"{v:.2f} MPa > 2.20 MPa threshold",
                "issue":     "High Compressor Discharge Pressure (Head Pressure)",
                "severity":  "High",
                "status":    "Current",
                "root_cause": (
                    "High discharge pressure is caused by restricted cooling water flow, "
                    "dirty/scaled condenser tubes, or refrigerant overcharge."
                ),
                "recommended_action": (
                    "1. Check cooling water pump and water flow rate. "
                    "2. Clean/descale condenser tubes. 3. Verify refrigerant charge."
                )
            },
            {
                "condition": lambda v: v < 1.40,
                "computed":  lambda v: f"{v:.2f} MPa < 1.40 MPa threshold",
                "issue":     "Low Compressor Discharge Pressure",
                "severity":  "Medium",
                "status":    "Current",
                "root_cause": (
                    "Low discharge pressure indicates low refrigerant charge, compressor valve "
                    "leakage, or extremely cold condenser inlet water."
                ),
                "recommended_action": (
                    "1. Check refrigerant charge. 2. Verify compressor pumping capacity. "
                    "3. Regulate condenser water bypass."
                )
            }
        ]
    },

    # ── WATER INLET TEMP ─────────────────────────────────────────
    {
        "sensor":      "water_inlet_temp_c",
        "label":       "Water Inlet Temperature (°C)",
        "unit":        "°C",
        "normal_min":  20.0,
        "normal_max":  35.0,
        "checks": [
            {
                "condition": lambda v: v > 35.0,
                "computed":  lambda v: f"{v:.1f} °C > 35.0 °C threshold",
                "issue":     "High Cooling Water Inlet Temperature",
                "severity":  "High",
                "status":    "Current",
                "root_cause": (
                    "Cooling water entering the condenser is too warm. This restricts the condenser's "
                    "heat rejection capacity, raising discharge pressure and reducing efficiency."
                ),
                "recommended_action": (
                    "1. Check cooling tower fan and operation. "
                    "2. Verify cooling tower water level and make-up system."
                )
            },
            {
                "condition": lambda v: v < 20.0,
                "computed":  lambda v: f"{v:.1f} °C < 20.0 °C threshold",
                "issue":     "Low Cooling Water Inlet Temperature",
                "severity":  "Low",
                "status":    "Current",
                "root_cause": (
                    "Cooling water entering is colder than expected. While this improves efficiency, "
                    "extremely low temperatures can lead to low discharge pressures."
                ),
                "recommended_action": (
                    "1. Monitor system operations. "
                    "2. Adjust cooling tower bypass valve if necessary."
                )
            }
        ]
    },

    # ── WATER OUTLET TEMP ────────────────────────────────────────
    {
        "sensor":      "water_outlet_temp_c",
        "label":       "Water Outlet Temperature (°C)",
        "unit":        "°C",
        "normal_min":  21.0,
        "normal_max":  40.0,
        "checks": [
            {
                "condition": lambda v: v > 40.0,
                "computed":  lambda v: f"{v:.1f} °C > 40.0 °C threshold",
                "issue":     "High Cooling Water Outlet Temperature",
                "severity":  "High",
                "status":    "Current",
                "root_cause": (
                    "Condenser outlet water temperature is dangerously high. This indicates a high "
                    "condenser heat load combined with insufficient water flow or scaled tubes."
                ),
                "recommended_action": (
                    "1. Increase water flow rate. "
                    "2. Clean/descale condenser tubes."
                )
            }
        ]
    },

    # ── COMPRESSOR CURRENT ───────────────────────────────────────
    {
        "sensor":      "compressor_amperes",
        "label":       "Compressor Current (A)",
        "unit":        "A",
        "normal_min":  10.0,
        "normal_max":  45.0,
        "checks": [
            {
                "condition": lambda v: v > 45.0,
                "computed":  lambda v: f"{v:.1f} A > 45.0 A threshold",
                "issue":     "Overloaded Compressor Current",
                "severity":  "Critical",
                "status":    "Current",
                "root_cause": (
                    "Compressor motor current draw exceeds safe limits. This indicates mechanical binding, "
                    "electrical short, or excessive operating pressures (high head pressure)."
                ),
                "recommended_action": (
                    "1. Check discharge pressure and water cooling flow. "
                    "2. Verify motor winding insulation resistance. 3. Inspect compressor run capacitor."
                )
            },
            {
                "condition": lambda v: 0.1 < v < 10.0,
                "computed":  lambda v: f"{v:.1f} A < 10.0 A threshold",
                "issue":     "Low Compressor Current (Underload)",
                "severity":  "Medium",
                "status":    "Current",
                "root_cause": (
                    "Compressor is drawing very low current while running. This suggests the compressor "
                    "is running underloaded, commonly due to major refrigerant loss."
                ),
                "recommended_action": (
                    "1. Test refrigerant pressures. "
                    "2. Check for leaks in the coil and fittings."
                )
            }
        ]
    },

    # ── AC OUTLET TEMPERATURE ────────────────────────────────────
    {
        "sensor":      "ac_outlet_temp",
        "label":       "AC Supply Outlet Temp (°C)",
        "unit":        "°C",
        "normal_min":  12.0,
        "normal_max":  24.0,
        "checks": [
            {
                "condition": lambda v: v > 24.0,
                "computed":  lambda v: f"{v:.1f} °C > 24.0 °C threshold",
                "issue":     "Poor Cooling Output / High Supply Temp",
                "severity":  "High",
                "status":    "Current",
                "root_cause": (
                    "AC supply air temperature is too warm, suggesting the unit is failing to cool the "
                    "space (compressor issue, low charge, or dirty evaporator)."
                ),
                "recommended_action": (
                    "1. Clean return air filter and evaporator coil. "
                    "2. Verify compressor is running and pumping."
                )
            },
            {
                "condition": lambda v: v < 12.0,
                "computed":  lambda v: f"{v:.1f} °C < 12.0 °C threshold",
                "issue":     "Extremely Low AC Supply Temp (Freezing Risk)",
                "severity":  "Medium",
                "status":    "Current",
                "root_cause": (
                    "Supply temperature is very low, indicating the evaporator coil is approaching "
                    "freezing conditions (restricting air flow or low refrigerant)."
                ),
                "recommended_action": (
                    "1. Clean return filter to improve airflow. "
                    "2. Verify fan motor speed."
                )
            }
        ]
    },

    # ── WATER TEMP DIFF ──────────────────────────────────────────
    {
        "sensor":      "water_temp_diff",
        "label":       "Water Heat Exchange Temp Difference (°C)",
        "unit":        "°C",
        "normal_min":  0.5,
        "normal_max":  15.0,
        "checks": [
            {
                "condition": lambda v: v <= 0.2,
                "computed":  lambda v: f"{v:.1f} °C <= 0.2 °C threshold",
                "issue":     "Inefficient Heat Exchange (Water Outlet Temp <= Inlet Temp)",
                "severity":  "High",
                "status":    "Current",
                "root_cause": (
                    "Condenser cooling water temperature difference is close to zero while "
                    "the compressor is active. This indicates cooling water flow blockage, "
                    "pump failure, or severe refrigeration cycle fault."
                ),
                "recommended_action": (
                    "1. Check water cooling pump operation. 2. Verify water valves are fully open. "
                    "3. Inspect refrigerant charge and compressor."
                )
            }
        ]
    },

    # ── COMPRESSOR PRESSURE DIFFERENTIAL ─────────────────────────
    {
        "sensor":      "compressor_pressure_diff",
        "label":       "Compressor Pressure Differential (MPa)",
        "unit":        "MPa",
        "normal_min":  0.5,
        "normal_max":  2.0,
        "checks": [
            {
                "condition": lambda v: v < 0.3,
                "computed":  lambda v: f"{v:.2f} MPa < 0.30 MPa threshold",
                "issue":     "Low Pressure Differential (Discharge - Suction)",
                "severity":  "High",
                "status":    "Current",
                "root_cause": (
                    "The difference between discharge and suction pressure is unusually low "
                    "while the compressor is drawing current. This indicates compressor valve leakage, "
                    "internal bypass, or failing pump mechanical parts."
                ),
                "recommended_action": (
                    "1. Check compressor valves. 2. Test compressor pumping capacity."
                )
            }
        ]
    }
]


# ─────────────────────────────────────────────────────────────
# MAIN FUNCTION
# ─────────────────────────────────────────────────────────────

def analyze_with_rules(telemetry: dict) -> dict:
    """
    Run all physics-based rules against a telemetry reading.

    Algorithm Steps
    ───────────────
    1. For each sensor rule in RULES:
        a. Extract the sensor value from telemetry (skip if missing)
        b. Convert to float
        c. Compare against each threshold check (condition lambda)
        d. If triggered → build a finding dict with:
             - sensor, value, computed expression, issue,
               severity, status, root_cause, recommended_action
    2. Compute an overall severity score:
         Critical=4, High=3, Medium=2, Low=1
         overall = highest individual severity
    3. Return:
         {
           "findings":          [...],   # list of triggered rules
           "overall_severity":  str,     # worst severity found
           "sensors_checked":   int,     # number of sensors evaluated
           "sensors_triggered": int,     # number of sensors that fired a rule
           "computation_steps": [...]    # human-readable audit trail
         }

    Args:
        telemetry (dict): Sensor key → numeric value mapping.

    Returns:
        dict: Rule engine result payload.
    """
    # Work on a copy of telemetry to avoid side effects
    telemetry = dict(telemetry)

    # Calculate virtual sensors for water temperature difference
    if 'water_inlet_temp_c' in telemetry and 'water_outlet_temp_c' in telemetry:
        try:
            in_t = float(telemetry['water_inlet_temp_c'])
            out_t = float(telemetry['water_outlet_temp_c'])
            comp_a_str = telemetry.get('compressor_amperes')
            comp_a = float(comp_a_str) if comp_a_str is not None else 0.0
            
            suc_str = str(telemetry.get('compressor_suction_pressure', '')).strip().upper()
            dis_str = str(telemetry.get('compressor_discharge_pressure', '')).strip().upper()
            is_off = (suc_str == 'OFF' or dis_str == 'OFF' or comp_a < 1.0)
            
            if not is_off and comp_a > 10.0:
                telemetry['water_temp_diff'] = out_t - in_t
        except (ValueError, TypeError):
            pass

    # Calculate virtual sensors for compressor pressure differential
    if 'compressor_suction_pressure' in telemetry and 'compressor_discharge_pressure' in telemetry:
        try:
            suc_p = float(telemetry['compressor_suction_pressure'])
            dis_p = float(telemetry['compressor_discharge_pressure'])
            comp_a_str = telemetry.get('compressor_amperes')
            comp_a = float(comp_a_str) if comp_a_str is not None else 0.0
            
            suc_str = str(telemetry.get('compressor_suction_pressure', '')).strip().upper()
            dis_str = str(telemetry.get('compressor_discharge_pressure', '')).strip().upper()
            is_off = (suc_str == 'OFF' or dis_str == 'OFF' or comp_a < 1.0)
            
            if not is_off and comp_a > 5.0:
                telemetry['compressor_pressure_diff'] = dis_p - suc_p
        except (ValueError, TypeError):
            pass

    findings = []
    computation_steps = []
    severity_rank = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}
    overall_severity = None
    sensors_checked = 0
    sensors_triggered = 0

    for rule in RULES:
        sensor_key = rule["sensor"]
        raw_value = telemetry.get(sensor_key)

        # ── Step 1: Value extraction ───────────────────────────
        if raw_value is None:
            computation_steps.append({
                "sensor": rule["label"],
                "value": "N/A",
                "normal_range": f"{rule['normal_min']} – {rule['normal_max']} {rule['unit']}".strip(),
                "result": "SKIPPED",
                "reason": "Sensor data not present in telemetry payload",
            })
            continue

        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            computation_steps.append({
                "sensor": rule["label"],
                "value": str(raw_value),
                "normal_range": f"{rule['normal_min']} – {rule['normal_max']} {rule['unit']}".strip(),
                "result": "SKIPPED",
                "reason": "Non-numeric value — cannot evaluate",
            })
            continue

        sensors_checked += 1
        rule_triggered = False

        # ── Step 2: Evaluate each threshold check ──────────────
        for check in rule["checks"]:
            triggered = False
            try:
                triggered = check["condition"](value)
            except Exception:
                pass

            if triggered:
                rule_triggered = True
                computed_expr = check["computed"](value)
                finding = {
                    "sensor":              rule["label"],
                    "sensor_key":          sensor_key,
                    "measured_value":      value,
                    "unit":                rule["unit"],
                    "normal_range":        f"{rule['normal_min']} – {rule['normal_max']} {rule['unit']}".strip(),
                    "computed_expression": computed_expr,
                    "issue":               check["issue"],
                    "severity":            check["severity"],
                    "status":              check["status"],
                    "root_cause":          check["root_cause"],
                    "recommended_action":  check["recommended_action"],
                }
                findings.append(finding)

                # Track overall worst severity
                rank = severity_rank.get(check["severity"], 0)
                if overall_severity is None or rank > severity_rank.get(overall_severity, 0):
                    overall_severity = check["severity"]

                computation_steps.append({
                    "sensor":       rule["label"],
                    "value":        f"{value} {rule['unit']}".strip(),
                    "normal_range": f"{rule['normal_min']} – {rule['normal_max']} {rule['unit']}".strip(),
                    "result":       "TRIGGERED",
                    "expression":   computed_expr,
                    "severity":     check["severity"],
                    "issue":        check["issue"],
                })
            else:
                # Only log a PASS step if no other check for this rule triggered
                if not rule_triggered:
                    pass  # Will log PASS below after all checks

        # ── Step 3: Log PASS if no check triggered ─────────────
        if not rule_triggered:
            computation_steps.append({
                "sensor":       rule["label"],
                "value":        f"{value} {rule['unit']}".strip(),
                "normal_range": f"{rule['normal_min']} – {rule['normal_max']} {rule['unit']}".strip(),
                "result":       "PASS",
                "reason":       "Value within normal operating range",
            })
        else:
            sensors_triggered += 1

    return {
        "findings":          findings,
        "overall_severity":  overall_severity or "Normal",
        "sensors_checked":   sensors_checked,
        "sensors_triggered": sensors_triggered,
        "computation_steps": computation_steps,
    }
