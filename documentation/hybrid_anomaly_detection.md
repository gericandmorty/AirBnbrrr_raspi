# Hybrid Anomaly Detection System

This document explains the anomaly detection and alert analysis system used in AirBnBrrr. It covers the full pipeline from sensor data ingestion to the alert detail page, including the rule-based algorithm added to complement the AI layer.

---

## Overview

The system uses a **three-layer approach** to detect and diagnose AC anomalies:

| Layer | Method | Always Runs? | Requires Internet? |
|---|---|---|---|
| 1. Isolation Forest | Machine learning (statistical outlier detection) | Yes | No |
| 2. Rule Engine | Physics-based threshold checks | Yes | No |
| 3. AI / LLM | Contextual language model diagnosis | Only if Layer 1 triggers | Yes |

The key improvement is **Layer 2** — a deterministic rule engine that runs independently of the AI and produces verifiable, explainable findings grounded in the AC unit's engineering specifications.

---

## Why AI Alone Is Not Reliable

| Problem | Impact |
|---|---|
| Hallucination | AI can invent faults that don't exist |
| API dependency | If the API is offline, no diagnosis is produced |
| Inconsistency | Same input can produce different outputs across calls |
| Black box | Results cannot be independently verified |
| No hard specs | AI doesn't inherently know your AC's rated wattage, voltage range, etc. |

The rule engine solves all of these problems for known, measurable sensor thresholds.

---

## Files Changed / Added

### New File: `services/rule_engine.py`

The rule engine. Contains:
- `RULES` — a list of sensor rule definitions, each with threshold checks and human-readable descriptions
- `analyze_with_rules(telemetry: dict) -> dict` — the main function

### Modified File: `services/anomaly_reciever.py`

Updated to run the rule engine **before** calling the AI. Both results are now stored together in the alert's `diagnoses` field as a combined JSON structure.

### Modified File: `templates/pages/alert.html`

Redesigned alert detail page with:
- Two-panel layout: **Automatic Safety Checks** (rule engine) and **AI Expert Opinion**
- Visual range bars showing where each sensor reading falls relative to its safe zone
- Friendly sensor names and plain-English labels
- Numbered action steps
- Top status banner summarizing overall severity
- Collapsible technical computation steps table (for review/audit)

### Utility Files (can be deleted after use)

| File | Purpose |
|---|---|
| `test_alert_inject.py` | Injects a simulated anomaly alert for testing |
| `fix_alerts_id.py` | One-time migration: adds auto-increment sequence to `alerts.id` |
| `check_schema.py` | Diagnostic: prints the `alerts` table column definitions |

---

## How the Rule Engine Works

### Algorithm Steps

```
For each sensor rule in RULES:
  1. Extract the sensor value from the telemetry dict
     → Skip if the value is missing or non-numeric (logged as SKIPPED)
  2. Convert to float
  3. Evaluate each threshold condition (a Python lambda)
     → If triggered: record a finding with:
          sensor name, measured value, normal range,
          computed expression, issue, severity,
          root cause, recommended action
  4. Track the worst overall severity seen across all sensors
  5. Append to computation_steps (TRIGGERED / PASS / SKIPPED)

Return:
  {
    "findings":          [ list of triggered rules ],
    "overall_severity":  "High" | "Medium" | "Low" | "Normal",
    "sensors_checked":   int,
    "sensors_triggered": int,
    "computation_steps": [ audit trail of every sensor evaluated ]
  }
```

### Threshold Definitions

All thresholds are derived from the AC unit's engineering specifications:

| Sensor | Safe Range | Low Alert | High Alert |
|---|---|---|---|
| `pzem_power` | 545 – 600 W | < 545 W → Compressor failed to start | > 600 W → Compressor overload |
| `pzem_voltage` | 210 – 240 V | < 210 V → Undervoltage | > 240 V → Overvoltage |
| `pzem_frequency` | 59 – 61 Hz | — | Outside range → Grid instability |
| `pzem_power_factor` | 0.85 – 1.0 | < 0.85 → Capacitor degradation | — |
| `ds18b20_temp1` (discharge) | 55 – 90 °C | < 55 °C → Low refrigerant | > 90 °C → Dirty condenser / overheating |
| `ds18b20_temp2` (suction) | 5 – 20 °C | < 4 °C → Evaporator freezing | > 20 °C → Refrigerant loss |
| `vibration` | 0 – 0.5 g | — | > 0.5 g → Loose mount / mechanical wear |
| `dust_sensor` | 0 – 300 | — | > 300 → Dirty air filter |

---

## Combined Diagnoses Storage Format

When an anomaly is processed, both rule and AI results are stored together in the `alerts.diagnoses` column as a single JSON string:

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

> **Backward compatibility:** Old alerts that only contain AI diagnoses (`{"diagnoses": [...]}`) are still rendered correctly. The frontend detects the format and falls back to legacy rendering.

---

## Alert Pipeline Flow

```
Raspberry Pi
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
    └─▶ LAYER 2: process_anomaly() triggered
            │
            ├─▶ Rule Engine (always runs first)
            │       analyze_with_rules(telemetry)
            │       Checks all 8 sensor thresholds
            │       Produces findings + computation_steps
            │
            ├─▶ AI / LLM (runs second)
            │       Sends formatted telemetry to Gemini/OpenAI
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

## Testing: Injecting a Simulated Anomaly

The file `test_alert_inject.py` creates a test alert with all sensors in an out-of-range state to verify the full pipeline:

```bash
venv\Scripts\python test_alert_inject.py
```

**Simulated values used:**

| Sensor | Value | Expected Rule |
|---|---|---|
| `pzem_power` | 651.2 W | Compressor Overload (High) |
| `pzem_voltage` | 207.4 V | Undervoltage (Medium) |
| `pzem_power_factor` | 0.71 | Capacitor Degradation (Medium) |
| `ds18b20_temp1` | 96.3 °C | High Discharge Temp (High) |
| `ds18b20_temp2` | 2.1 °C | Evaporator Freezing (High) |
| `vibration` | 0.87 g | Excessive Vibration (Medium) |
| `dust_sensor` | 480 | Dirty Filter (Low) |
| `pzem_frequency` | 60.1 Hz | **PASS** — within range |

The script prints the computation steps to the terminal, then POSTs the alert to the running server and prints the URL to view it.

---

## Database Note: alerts.id Auto-Increment

The `alerts` table's `id` column originally had no default sequence. The file `fix_alerts_id.py` is a one-time migration that adds the auto-increment default:

```python
cur.execute("CREATE SEQUENCE IF NOT EXISTS alerts_id_seq")
cur.execute("SELECT setval('alerts_id_seq', COALESCE((SELECT MAX(id) FROM alerts), 0) + 1, false)")
cur.execute("ALTER TABLE alerts ALTER COLUMN id SET DEFAULT nextval('alerts_id_seq')")
```

This only needs to be run once per database.
