# Hybrid Anomaly Detection System

This document explains the anomaly detection and alert analysis system used in AirBnBrrr. It covers the full pipeline from sensor data ingestion to the alert detail page, including a detailed, plain-English walkthrough of the rule-based algorithm that runs on your backend.

---

## Overview

The system uses a **three-layer approach** to detect and diagnose air conditioner (AC) anomalies:

| Layer | Method | Always Runs? | Requires Internet? |
|---|---|---|---|
| **1. Isolation Forest** | Machine learning (statistical outlier detection) | Yes | No |
| **2. Rule Engine** | Physics-based threshold checks | Yes | No |
| **3. AI / LLM** | Contextual language model diagnosis | Only if Layer 1 triggers | Yes |

The key improvement is **Layer 2 (Rule Engine)** — a deterministic rule engine that runs independently of the AI and produces verifiable, explainable findings grounded in the AC unit's engineering specifications.

---

## Why AI Alone Is Not Reliable

| Problem | Impact |
|---|---|
| **Hallucination** | AI can invent faults that don't exist in the physical system |
| **API dependency** | If the internet is down or the AI server is offline, no diagnosis is produced |
| **Inconsistency** | The same sensor readings can produce different diagnoses across calls |
| **Black box** | Results cannot be audited or verified by a technician |
| **No hard specs** | The AI doesn't inherently know your AC's rated wattage, voltage limits, or coolant properties |

The rule engine solves all of these problems by verifying known, physical sensor thresholds.

---

## Complete Rule Engine Code (`services/rule_engine.py`)

Here is the complete source code for the rule engine implemented in the system:

```python
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

# THRESHOLD DEFINITIONS
RULES = [
    # ── POWER (W) ──
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

    # ── VOLTAGE (V) ──
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

    # ── FREQUENCY (Hz) ──
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

    # ── POWER FACTOR ──
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

    # ── DISCHARGE LINE TEMPERATURE (ds18b20_temp1) ──
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

    # ── SUCTION LINE TEMPERATURE (ds18b20_temp2) ──
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

    # ── VIBRATION (g) ──
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

    # ── DUST SENSOR ──
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

def analyze_with_rules(telemetry: dict) -> dict:
    findings = []
    computation_steps = []
    severity_rank = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}
    overall_severity = None
    sensors_checked = 0
    sensors_triggered = 0

    for rule in RULES:
        sensor_key = rule["sensor"]
        raw_value = telemetry.get(sensor_key)

        # Step A: Value extraction & Validation
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

        # Step B: Evaluate each threshold condition check
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

                # Keep track of the worst overall severity triggered
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

        # Step C: Log PASS if no checks were triggered
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
```

---

## Plain-English Walkthrough (Function-by-Function)

The rule engine acts like a strict HVAC inspector who checks the physical metrics of your AC against its manufacturing catalog guidelines.

### The Entrypoint: `analyze_with_rules(telemetry)`

This is the main function. When a new set of sensor data (telemetry) arrives from the ESP32, this function is called. Here is what it does step-by-step in plain English:

1. **Sets up the Scoreboard**: It prepares an empty list to record any problems (findings), an audit trail (computation steps), and initializes a count of how many sensors it has evaluated.
2. **Loops Through the Rules**: It goes through the list of 8 physical guidelines (the `RULES` array) one by one.
3. **Step A — Grabs and Cleans the Data**:
   * It looks for the sensor key in the incoming packet (e.g., `pzem_power`).
   * If a sensor's data is missing entirely (like if the dust sensor is temporarily disconnected), it marks the check as `SKIPPED` and moves on to the next sensor so it doesn't crash the program.
   * If the data is text instead of a number, it also marks it as `SKIPPED`.
4. **Step B — Evaluates the Limits**:
   * For each active sensor, it tests the current value against the target limits defined in the rule checks.
   * If a value crosses a threshold (like power going above 600 Watts), the rule triggers.
   * When triggered, it records a detailed **finding**: what sensor is failing, what the value was, the normal range, the issue name, severity, root cause description, and step-by-step recommended fix instructions.
   * It adds this event to the audit trail (`computation_steps`) as `TRIGGERED`.
   * It compares this issue's severity (Low, Medium, High, or Critical) with the worst issue found so far during this scan, updating the overall severity scoreboard.
5. **Step C — Approves Good Readings**:
   * If a sensor was successfully scanned and did not break any limits, it is logged as a `PASS` in the audit trail.
6. **Compiles the Report Card**:
   * Finally, it packages all the detailed findings, the overall severity, the total number of sensors scanned, and the full audit trail into a final document and returns it.

---

## Sensor Rules & Thresholds Explained

Here are the 8 diagnostic rules the algorithm uses, explained in plain language:

### 1. Power Consumption Check (`pzem_power`)
This checks the actual electrical work being done by the AC unit.
* **Normal Range**: 545.0 W to 600.0 W (rated range of the 0.6 HP compressor).
* **Checks**:
  * **Over 600.0 W (High Severity)**: The unit is drawing too much power. This means the compressor is struggling under high pressure, likely due to a dirty condenser coil blocking airflow or a degrading run capacitor causing the motor to draw extra power.
  * **Between 0.0 W and 545.0 W (High Severity)**: Suspects the compressor failed to start. Only the fan is drawing power (≈50–80W) but no cooling is happening. This is usually caused by a bad starter capacitor or a stuck thermostat mode.
  * **Exactly 0.0 W (Critical Severity)**: No electricity is being drawn. The AC is completely off, unplugged, or has tripped a circuit breaker.

### 2. Supply Voltage Check (`pzem_voltage`)
This monitors the grid power quality feeding the air conditioner.
* **Normal Range**: 210.0 V to 240.0 V.
* **Checks**:
  * **Under 210.0 V (Medium Severity)**: Low voltage. This is dangerous because motors draw more current to compensate for low voltage, causing components to overheat and rapidly wear out.
  * **Over 240.0 V (Medium Severity)**: Overvoltage. High electrical pressure that stresses circuit boards, capacitors, and motor windings.

### 3. Grid Frequency Check (`pzem_frequency`)
Checks the stability of the power grid.
* **Normal Range**: 59.0 Hz to 61.0 Hz (standard grid frequency is 60 Hz).
* **Checks**:
  * **Outside 59–61 Hz (Low Severity)**: Indicates minor power grid instability. This can make the AC motor run slightly slower or faster, decreasing efficiency.

### 4. Power Factor Check (`pzem_power_factor`)
Monitors the efficiency of electricity usage.
* **Normal Range**: 0.85 to 1.00.
* **Checks**:
  * **Under 0.85 (Medium Severity)**: Low power factor. This suggests the AC motor is drawing excessive current compared to the actual cooling power produced. In non-inverter ACs, this is a strong early indicator that the run capacitor is degrading.

### 5. Discharge Line Temperature (`ds18b20_temp1`)
Measures the temperature of the hot refrigerant gas leaving the compressor.
* **Normal Range**: 55.0 °C to 90.0 °C.
* **Checks**:
  * **Over 90.0 °C (High Severity)**: The compressor is running extremely hot. The condenser coil is likely choked with dust and can't release heat, or the system is low on refrigerant.
  * **Under 55.0 °C (Medium Severity)**: The compressor is active, but the refrigerant is not heating up. This suggests a low refrigerant charge (leak) or lack of pressure build-up.

### 6. Suction Line Temperature (`ds18b20_temp2`)
Measures the temperature of the cold refrigerant returning from the indoor cooling coil.
* **Normal Range**: 5.0 °C to 20.0 °C.
* **Checks**:
  * **Under 4.0 °C (High Severity)**: The cooling coil is freezing up and turning to ice. This is highly dangerous as liquid refrigerant can flow back and destroy the compressor. Usually caused by a completely blocked air filter.
  * **Over 20.0 °C (Medium Severity)**: The cold return pipe is warm. This indicates that the air conditioner is not absorbing heat from the room, likely due to severe refrigerant loss.

### 7. Compressor Vibration Check (`vibration`)
Measures the physical shaking of the compressor.
* **Normal Range**: 0.0 g to 0.5 g.
* **Checks**:
  * **Over 0.5 g (Medium Severity)**: Excessive shaking. Indicates that the rubber vibration mounts have hardened/cracked, or the mounting bolts have shaken loose.

### 8. Dust Level Check (`dust_sensor`)
Monitors dust levels inside the air intake.
* **Normal Range**: 0 to 300.
* **Checks**:
  * **Over 300 (Low Severity)**: The air filter is dirty and clogged, restricting airflow. This causes the AC to work harder and reduces cooling capacity.

---

## Combined Diagnoses Storage Format

When an anomaly is processed, both the rule engine results and the AI results are stored together in the `alerts.diagnoses` column of your database as a single JSON string:

```json
{
  "rule_diagnoses": {
    "findings": [
      {
        "sensor": "Power Consumption (W)",
        "sensor_key": "pzem_power",
        "measured_value": 651.2,
        "unit": "W",
        "normal_range": "545.0 – 600.0 W",
        "computed_expression": "651.2 W  >  600 W threshold",
        "issue": "Overloaded Compressor or Failing Run Capacitor",
        "severity": "High",
        "status": "Current",
        "root_cause": "...",
        "recommended_action": "1. Clean the condenser coil..."
      }
    ],
    "overall_severity": "High",
    "sensors_checked": 8,
    "sensors_triggered": 7,
    "computation_steps": [
      {
        "sensor": "Power Consumption (W)",
        "value": "651.2 W",
        "normal_range": "545.0 – 600.0 W",
        "result": "TRIGGERED",
        "expression": "651.2 W  >  600 W threshold",
        "severity": "High",
        "issue": "Overloaded Compressor or Failing Run Capacitor"
      }
    ]
  },
  "ai_diagnoses": {
    "diagnoses": [
      {
        "issue": "...",
        "status": "Current",
        "confidence_score": 96,
        "root_cause": "...",
        "severity": "Critical",
        "recommended_action": "..."
      }
    ]
  }
}
```

---

## Alert Pipeline Flow

```
Raspberry Pi / ESP32
    │
    ▼ POST /telemetry
FastAPI (main.py)
    │
    ├─▶ Store raw values in DB (telemetry table)
    │
    ├─▶ LAYER 1: Isolation Forest
    │       Trained on historical data at startup
    │       Returns -1 (anomaly) or 1 (normal)
    │       If normal → stop, no alert
    │
    └─▶ LAYER 2: process_telemetry_background() triggered (in BackgroundTasks)
            │
            ├─▶ Rule Engine (always runs first)
            │       analyze_with_rules(telemetry)
            │       Checks all 8 sensor thresholds
            │       Produces findings + computation_steps
            │
            ├─▶ AI / LLM (runs second)
            │       Sends formatted telemetry to AI API
            │       Returns JSON diagnoses with confidence scores
            │       If unavailable → stored as {"error": "..."}
            │
            ├─▶ Combine both into combined_diagnoses JSON
            │
            ├─▶ Save to alerts table
            │
            └─▶ Send SMS via Traccar
```

---

## Alert Detail Page: UI Panels

### Automatic Safety Checks (Rule Engine Panel)

- **Status banner** — top-level colored alert: "High — 7 of 8 sensors outside safe limits"
- **Summary row** — sensors checked vs problems found
- **Per-finding cards**, each showing:
  - Sensor icon + friendly name (e.g., "Power Usage" instead of `pzem_power`)
  - Visual range bar — green safe zone, red/green dot for your reading
  - "Happening now" or "Possible future issue"
  - Plain-English explanation
  - Numbered "What to do" steps
- **Computation steps table** (collapsed by default) — full audit trail for technical review

### AI Expert Opinion (AI Panel)

- Per-finding cards showing:
  - Severity badge + "Happening now / Possible future issue"
  - AI confidence bar (visual progress bar, color-coded)
  - Plain-English explanation
  - Numbered action steps

---

## Layer 3: AI Diagnostic Reasoning Engine

When the Isolation Forest flags an anomaly, and after the Rule Engine performs its checks, Layer 3 (AI / LLM) is triggered in the background.

### API Integration & Platform
* **Provider**: **Cerebras Inference** (an ultra-fast hardware-accelerated inference API compatible with the OpenAI format).
* **Default Model**: **`zai-glm-4.7`** (a highly capable reasoning model configured to identify electrical/mechanical anomalies and suggest diagnostic paths).
* **Customization**: The API endpoint, model, and API Key are fully customizable via the **AI Setup** page on the dashboard and stored in the database.

### Sanitization and Parsing Layer
Since LLMs often return output wrapped in Markdown formatting (e.g. ```` ```json ... ``` ````), a dedicated sanitization parser was introduced to prevent JSON load failures:
1. **Backend Sanitization ([services/anomaly_reciever.py](file:///home/gericmorit/Desktop/Projects/client/main/raspi/services/anomaly_reciever.py))**: Strips any markdown fences and extracts the raw JSON string between the outermost `{` and `}` braces before storing the payload.
2. **Frontend Sanitization ([alert.html](file:///home/gericmorit/Desktop/Projects/client/main/raspi/templates/pages/alert.html))**: Employs an matching JS function `cleanAndParseJSON()` as a fallback to ensure historical or unparsed outputs saved in the database render correctly in the browser without UI breakage.

---

## Testing: Injecting a Simulated Anomaly

The file `send_mock_anomaly.py` sends a test telemetry reading with all sensors in an out-of-range state to verify the full pipeline:

```bash
python send_mock_anomaly.py
```

**Simulated values used:**

| Sensor | Value | Expected Rule |
|---|---|---|
| `pzem_power` | 673.2 W | Compressor Overload (High) |
| `pzem_voltage` | 204.0 V | Undervoltage (Medium) |
| `pzem_power_factor` | 0.72 | Capacitor Degradation (Medium) |
| `ds18b20_temp1` | 96.5 °C | High Discharge Temp (High) |
| `ds18b20_temp2` | 2.5 °C | Evaporator Freezing (High) |
| `vibration` | 0.82 g | Excessive Vibration (Medium) |
| `dust_sensor` | 350 | Dirty Filter (Low) |
| `pzem_frequency` | 60.0 Hz | **PASS** — within range |

The script prints the response from the server. The server then processes it in the background, evaluates the rules, asks the AI, stores the alert, and dispatches the SMS.
