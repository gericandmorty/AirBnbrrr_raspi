"""
Rule-Based Anomaly Detection Engine for AirBnBrrr
===================================================
A deterministic, physics-based algorithm that checks sensor readings
against hard-coded thresholds derived from the AC unit specifications.

AC Unit Specifications (reference for all thresholds):
  - Capacity     : 0.6 HP (5,400 BTU/h)
  - Type         : Manual Window Type (Non-Inverter)
  - Refrigerant  : R410A
  - Power Range  : 545W – 600W at full cooling
  - Voltage      : 220V – 230V / 60 Hz / 1-Phase
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
        "normal_min":  545.0,
        "normal_max":  600.0,
        "checks": [
            {
                "condition": lambda v: v > 600.0,
                "computed":  lambda v: f"{v:.1f} W  >  600 W threshold",
                "issue":     "Overloaded Compressor or Failing Run Capacitor",
                "severity":  "High",
                "status":    "Current",
                "root_cause": (
                    "Power draw exceeds the rated maximum of 600 W. "
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
                "condition": lambda v: 0 < v < 545.0,
                "computed":  lambda v: f"{v:.1f} W  <  545 W threshold",
                "issue":     "Compressor Failed to Start (Fan-Only Mode Suspected)",
                "severity":  "High",
                "status":    "Current",
                "root_cause": (
                    "Power draw is significantly below 545 W but above 0 W, "
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
        "normal_min":  210.0,
        "normal_max":  240.0,
        "checks": [
            {
                "condition": lambda v: v < 210.0,
                "computed":  lambda v: f"{v:.1f} V  <  210 V threshold",
                "issue":     "Undervoltage — Risk of Motor Overheating",
                "severity":  "Medium",
                "status":    "Current",
                "root_cause": (
                    "Supply voltage is below the safe operating minimum of 210 V. "
                    "Low voltage forces the compressor motor to draw higher current "
                    "to maintain torque, causing excess heat and accelerating winding degradation."
                ),
                "recommended_action": (
                    "1. Report the low voltage to your electrical utility. "
                    "2. Consider installing a voltage stabilizer/AVR. "
                    "3. Avoid running the AC unit until voltage stabilizes above 215 V."
                ),
            },
            {
                "condition": lambda v: v > 240.0,
                "computed":  lambda v: f"{v:.1f} V  >  240 V threshold",
                "issue":     "Overvoltage — Risk of Component Damage",
                "severity":  "Medium",
                "status":    "Current",
                "root_cause": (
                    "Supply voltage exceeds 240 V. High voltage stresses capacitors, "
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

    # ── DISCHARGE LINE TEMPERATURE (ds18b20_temp1) ─────────────
    {
        "sensor":      "ds18b20_temp1",
        "label":       "Discharge Line Temperature (°C)",
        "unit":        "°C",
        "normal_min":  55.0,
        "normal_max":  90.0,
        "checks": [
            {
                "condition": lambda v: v > 90.0,
                "computed":  lambda v: f"{v:.1f} °C  >  90 °C threshold",
                "issue":     "High Discharge Temp — Dirty Condenser or Low Refrigerant",
                "severity":  "High",
                "status":    "Current",
                "root_cause": (
                    "Compressor discharge line temperature exceeds 90 °C. "
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
                "condition": lambda v: v < 55.0 and v > 0,
                "computed":  lambda v: f"{v:.1f} °C  <  55 °C threshold",
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

    # ── SUCTION LINE TEMPERATURE (ds18b20_temp2) ───────────────
    {
        "sensor":      "ds18b20_temp2",
        "label":       "Suction Line Temperature (°C)",
        "unit":        "°C",
        "normal_min":  5.0,
        "normal_max":  20.0,
        "checks": [
            {
                "condition": lambda v: v < 4.0 and v > -10,
                "computed":  lambda v: f"{v:.1f} °C  <  4 °C (freezing threshold)",
                "issue":     "Evaporator Freezing — Blocked Airflow or Low Refrigerant",
                "severity":  "High",
                "status":    "Current",
                "root_cause": (
                    "Suction line temperature near or below 4 °C indicates the evaporator "
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
                "condition": lambda v: v > 20.0,
                "computed":  lambda v: f"{v:.1f} °C  >  20 °C threshold",
                "issue":     "High Suction Temp — Insufficient Cooling / Refrigerant Loss",
                "severity":  "Medium",
                "status":    "Current",
                "root_cause": (
                    "Suction line temperature above 20 °C indicates the refrigerant "
                    "is absorbing too little heat — often a sign of refrigerant loss, "
                    "very high ambient temperature, or a partially blocked metering device."
                ),
                "recommended_action": (
                    "1. Check ambient temperature — above 35 °C room temps stress any AC unit. "
                    "2. Have refrigerant pressure checked. "
                    "3. Inspect the filter/expansion valve if accessible."
                ),
            },
        ],
    },

    # ── VIBRATION (g) ──────────────────────────────────────────
    {
        "sensor":      "vibration",
        "label":       "Compressor Vibration (g)",
        "unit":        "g",
        "normal_min":  0.0,
        "normal_max":  0.5,
        "checks": [
            {
                "condition": lambda v: v > 0.5,
                "computed":  lambda v: f"{v:.2f} g  >  0.5 g threshold",
                "issue":     "Excessive Compressor Vibration — Mechanical Wear or Loose Mount",
                "severity":  "Medium",
                "status":    "Current",
                "root_cause": (
                    "Compressor vibration above 0.5 g is abnormal. "
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
        "label":       "Dust Level (behind filter)",
        "unit":        "raw units",
        "normal_min":  0,
        "normal_max":  300,
        "checks": [
            {
                "condition": lambda v: v > 300,
                "computed":  lambda v: f"{v:.0f}  >  300 (dirty filter threshold)",
                "issue":     "Dirty Air Filter — Restricted Airflow",
                "severity":  "Low",
                "status":    "Current",
                "root_cause": (
                    "The dust sensor behind the front filter reads above 300, "
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
