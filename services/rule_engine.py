"""
Rule-Based Anomaly Detection Engine for AirBnBrrr
===================================================
A deterministic safety check algorithm based on specifications:
1. Compressor Overheating (Current >= 8.8 A AND Power >= 1860 W AND Vibration >= 90 Hz)
2. Abnormal Compressor Vibration (Vibration >= 90 Hz)
3. High Dust Concentration (Dust >= 340 µg/m³)
4. Low Humidity (Humidity <= 80%)
"""

RULES = [
    {
        "id": "compressor_overheating",
        "label": "Compressor Overheating",
        "description": "Deterministic safety check for compressor thermal and load strain",
        "check": lambda tel: (
            float(tel.get("pzem_current", 0) or 0) >= 8.8 and 
            float(tel.get("pzem_power", 0) or 0) >= 1860.0 and 
            float(tel.get("vibration", 0) or 0) >= 90.0
        ),
        "issue": "Compressor Overheating",
        "severity": "High",
        "root_cause": "Indicates the compressor is under high electrical and mechanical load, commonly associated with reduced condenser cooling efficiency or compressor overloading.",
        "recommended_action": "Check whether the condenser fan is operating properly. Stop operating the air conditioner if the current continues to increase to prevent compressor damage and protect the electrical wiring and circuit breaker.",
        "normal_range": "Current < 8.8 A OR Power < 1860 W OR Vibration < 90 Hz",
        "measured_val_func": lambda tel: f"Current: {tel.get('pzem_current')} A, Power: {tel.get('pzem_power')} W, Vibration: {tel.get('vibration')} Hz",
        "unit": ""
    },
    {
        "id": "vibration",
        "label": "Abnormal Compressor Vibration",
        "description": "Deterministic safety check for mechanical looseness or wear",
        "check": lambda tel: (
            float(tel.get("vibration", 0) or 0) >= 90.0 and not (
                float(tel.get("pzem_current", 0) or 0) >= 8.8 and 
                float(tel.get("pzem_power", 0) or 0) >= 1860.0 and 
                float(tel.get("vibration", 0) or 0) >= 90.0
            )
        ),
        "issue": "Abnormal Compressor Vibration",
        "severity": "Medium",
        "root_cause": "Indicates excessive vibration that may result from compressor wear, loose mounting, or internal mechanical deterioration.",
        "recommended_action": "Inspect the compressor mounting, internal components, and check for signs of compressor wear or mechanical looseness.",
        "normal_range": "< 90 Hz",
        "measured_val_func": lambda tel: f"{tel.get('vibration')} Hz",
        "unit": "Hz"
    },
    {
        "id": "dust_sensor",
        "label": "High Dust Concentration",
        "description": "Deterministic safety check for clogged filter",
        "check": lambda tel: float(tel.get("dust_sensor", 0) or 0) >= 340.0,
        "issue": "High Dust Concentration",
        "severity": "Low",
        "root_cause": "Indicates excessive airborne dust that may clog the air filter or restrict airflow, reducing cooling efficiency.",
        "recommended_action": "Clean the air filter and inspect the evaporator section for dust accumulation that may restrict airflow.",
        "normal_range": "< 340 µg/m³",
        "measured_val_func": lambda tel: f"{tel.get('dust_sensor')} µg/m³",
        "unit": "µg/m³"
    },
    {
        "id": "dht_humidity",
        "label": "Low Humidity",
        "description": "Deterministic safety check for indoor coil cooling performance",
        "check": lambda tel: float(tel.get("dht_humidity", 100) or 100) <= 80.0,
        "issue": "Low Humidity",
        "severity": "Low",
        "root_cause": "Indicates reduced cooling performance or weak airflow from the indoor unit. Inspect the evaporator fan and verify that cold air is being discharged properly.",
        "recommended_action": "Check whether cold air is being discharged properly and inspect the evaporator fan for reduced airflow or malfunction.",
        "normal_range": "> 80 %",
        "measured_val_func": lambda tel: f"{tel.get('dht_humidity')} %",
        "unit": "%"
    },
    {
        "id": "reduced_cooling",
        "label": "Reduced Cooling Performance",
        "description": "Deterministic check: Outlet Compressor ≥ 64°C AND Output Air ≥ 21°C AND Inlet ≥ 22°C",
        "check": lambda tel: (
            float(tel.get("ds18b20_temp1", 0) or 0) >= 64.0 and
            float(tel.get("dht_temp", 0) or 0) >= 21.0 and
            float(tel.get("ds18b20_temp2", 0) or 0) >= 22.0
        ),
        "issue": "Reduced Cooling Performance",
        "severity": "Medium",
        "root_cause": "The monitored temperatures indicate a reduction in cooling performance. Inspect the refrigerant system for possible refrigerant leakage or insufficient refrigerant charge.",
        "recommended_action": "The monitored temperatures indicate a reduction in cooling performance. Inspect the refrigerant system for possible refrigerant leakage or insufficient refrigerant charge. Verify the condition using appropriate refrigeration service equipment and perform corrective maintenance if necessary.",
        "normal_range": "Outlet < 64°C OR Output < 21°C OR Inlet < 22°C",
        "measured_val_func": lambda tel: f"Outlet: {tel.get('ds18b20_temp1')}°C, Output: {tel.get('dht_temp')}°C, Inlet: {tel.get('ds18b20_temp2')}°C",
        "unit": "°C"
    }
]

def analyze_with_rules(telemetry: dict) -> dict:
    findings = []
    computation_steps = []
    severity_rank = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}
    overall_severity = None
    sensors_checked = 0
    sensors_triggered = 0

    for rule in RULES:
        sensors_checked += 1
        triggered = False
        try:
            triggered = rule["check"](telemetry)
        except Exception:
            pass

        measured_val = rule["measured_val_func"](telemetry)

        if triggered:
            finding = {
                "sensor":              rule["label"],
                "sensor_key":          rule["id"],
                "measured_value":      measured_val,
                "unit":                rule["unit"],
                "normal_range":        rule["normal_range"],
                "computed_expression": f"Triggered: {measured_val}",
                "issue":               rule["issue"],
                "severity":            rule["severity"],
                "status":              "Current",
                "root_cause":          rule["root_cause"],
                "recommended_action":  rule["recommended_action"],
            }
            findings.append(finding)

            rank = severity_rank.get(rule["severity"], 0)
            if overall_severity is None or rank > severity_rank.get(overall_severity, 0):
                overall_severity = rule["severity"]

            computation_steps.append({
                "sensor":       rule["label"],
                "value":        measured_val,
                "normal_range": rule["normal_range"],
                "result":       "TRIGGERED",
                "expression":   f"Value {measured_val} triggers threshold",
                "severity":     rule["severity"],
                "issue":        rule["issue"],
            })
            sensors_triggered += 1
        else:
            computation_steps.append({
                "sensor":       rule["label"],
                "value":        measured_val,
                "normal_range": rule["normal_range"],
                "result":       "PASS",
                "reason":       "Value within normal operating range",
            })

    return {
        "findings":          findings,
        "overall_severity":  overall_severity or "Normal",
        "sensors_checked":   sensors_checked,
        "sensors_triggered": sensors_triggered,
        "computation_steps": computation_steps,
    }
