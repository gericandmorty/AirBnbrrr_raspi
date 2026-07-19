from fastapi import FastAPI, HTTPException, Request, Response, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone, timedelta
import os

LOCAL_TZ = timezone(timedelta(hours=8))
from pathlib import Path
import subprocess
import threading
import time
from database import get_db_connection
from ac_setup import get_ac_setup, update_ac_setup
from web_routes import router as web_router, _read_template
from services.contacts_api import router as contacts_router
from services.alerts_api import router as alerts_router
from services.traccar_setup_api import router as traccar_setup_router
from services.ai_setup_api import router as ai_setup_router

from services.isolation_forest import AnomalyDetectorService
from services.traccar_sms import send_sms
from services.anomaly_reciever import process_anomaly
from services.auth import get_admin_from_token, verify_password, generate_session, clear_session

app = FastAPI(title="AirBnBrrr")

app.mount("/assets", StaticFiles(directory="assets"), name="assets")

app.include_router(web_router)
app.include_router(contacts_router)
app.include_router(alerts_router)
app.include_router(traccar_setup_router)
app.include_router(ai_setup_router)

service = AnomalyDetectorService(db_path='./telemetry.db')

class Item(BaseModel):
	id: int
	name: str
	description: Optional[str] = None


_fake_db: dict[int, dict] = {}


DB_PATH = Path("telemetry.db")


class Telemetry(BaseModel):
	ac_unit: Optional[str] = None
	dust_sensor: Optional[float] = None
	dht_temp: Optional[float] = None
	dht_humidity: Optional[float] = None
	vibration: Optional[float] = None
	ds18b20_temp1: Optional[float] = None
	ds18b20_temp2: Optional[float] = None
	pzem_voltage: Optional[float] = None
	pzem_current: Optional[float] = None
	pzem_power: Optional[float] = None
	pzem_energy: Optional[float] = None
	pzem_frequency: Optional[float] = None
	pzem_power_factor: Optional[float] = None
	ac_status: Optional[str] = None
	ac_thermostat: Optional[str] = None


class ACSetup(BaseModel):
	ac_status: Optional[str] = None
	ac_thermostat: Optional[str] = None
	data_gathering_mode: Optional[str] = None
	data_gathering_unit: Optional[str] = None


@app.on_event("startup")
def on_startup():
	pass


class LoginRequest(BaseModel):
	username: str
	password: str


@app.post("/api/login")
def api_login(payload: LoginRequest, response: Response):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("SELECT password FROM admin WHERE username = %s", (payload.username,))
	row = cur.fetchone()
	conn.close()

	if not row:
		raise HTTPException(status_code=401, detail="Invalid username or password")

	hashed = row["password"]
	if not verify_password(payload.password, hashed):
		raise HTTPException(status_code=401, detail="Invalid username or password")

	# Create session
	token, _ = generate_session(payload.username)

	response.set_cookie(
		key="admin_session",
		value=token,
		httponly=True,
		max_age=86400,  # 1 day
		samesite="lax",
	)
	return {"status": "success"}


@app.post("/api/logout")
@app.get("/api/logout")
def api_logout(request: Request, response: Response):
	token = request.cookies.get("admin_session")
	if token:
		clear_session(token)
	response.delete_cookie("admin_session")
	return RedirectResponse(url="/pages/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
	token = request.cookies.get("admin_session")
	if not get_admin_from_token(token):
		return RedirectResponse(url="/pages/login", status_code=303)
	return HTMLResponse(_read_template("control_panel.html"))


# Anomaly alert debouncer state
ALERT_DELAY_SECONDS = float(os.environ.get("ALERT_DELAY_SECONDS", "480.0"))
alert_timer = None
timer_lock = threading.Lock()

def trigger_alert_action(data):
	global alert_timer
	with timer_lock:
		alert_timer = None
	print(f"\n[DEBOUNCER] 8-minute delay completed. Processing anomaly alert...", flush=True)
	try:
		process_anomaly(data)
	except Exception as e:
		print(f"\n[ERROR] process_anomaly failed: {e}\n", flush=True)


def process_telemetry_background(payload_dict: dict):
	global alert_timer
	try:
		# Use AC setup values from the ac_setup table (single source of truth)
		ac_values = get_ac_setup()
		ac_status = ac_values.get("ac_status", "Not Set")
		ac_thermostat = ac_values.get("ac_thermostat", "Not Set")
		data_gathering_mode = ac_values.get("data_gathering_mode", "telemetry")
		data_gathering_unit = payload_dict.get("ac_unit") or ac_values.get("data_gathering_unit", "AC2")

		conn = get_db_connection()
		cur = conn.cursor()
		if data_gathering_mode == "data_gathered":
			cur.execute(
				"""
				INSERT INTO data_gathered (
					timestamp, ac_unit,
					dust_sensor, dht_temp, dht_humidity, vibration,
					ds18b20_temp1, ds18b20_temp2,
					pzem_voltage, pzem_current, pzem_power, pzem_energy,
					pzem_frequency, pzem_power_factor,
					ac_status, ac_thermostat
				) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
				RETURNING id
				""",
				(
					datetime.now(LOCAL_TZ),
					data_gathering_unit,
					payload_dict.get("dust_sensor"),
					payload_dict.get("dht_temp"),
					payload_dict.get("dht_humidity"),
					payload_dict.get("vibration"),
					payload_dict.get("ds18b20_temp1"),
					payload_dict.get("ds18b20_temp2"),
					payload_dict.get("pzem_voltage"),
					payload_dict.get("pzem_current"),
					payload_dict.get("pzem_power"),
					payload_dict.get("pzem_energy"),
					payload_dict.get("pzem_frequency"),
					payload_dict.get("pzem_power_factor"),
					ac_status,
					ac_thermostat,
				),
			)
			row_id = cur.fetchone()['id']
			print(f"\n[BACKGROUND] Telemetry stored in data_gathered table (unit {data_gathering_unit}) with ID {row_id}", flush=True)
		else:
			cur.execute(
				"""
				INSERT INTO telemetry (
					timestamp,
					dust_sensor, dht_temp, dht_humidity, vibration,
					ds18b20_temp1, ds18b20_temp2,
					pzem_voltage, pzem_current, pzem_power, pzem_energy,
					pzem_frequency, pzem_power_factor,
					ac_status, ac_thermostat
				) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
				RETURNING id
				""",
				(
					datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S"),
					payload_dict.get("dust_sensor"),
					payload_dict.get("dht_temp"),
					payload_dict.get("dht_humidity"),
					payload_dict.get("vibration"),
					payload_dict.get("ds18b20_temp1"),
					payload_dict.get("ds18b20_temp2"),
					payload_dict.get("pzem_voltage"),
					payload_dict.get("pzem_current"),
					payload_dict.get("pzem_power"),
					payload_dict.get("pzem_energy"),
					payload_dict.get("pzem_frequency"),
					payload_dict.get("pzem_power_factor"),
					ac_status,
					ac_thermostat,
				),
			)
			row_id = cur.fetchone()['id']
			print(f"\n[BACKGROUND] Telemetry successfully stored with ID {row_id}", flush=True)
		conn.commit()
		conn.close()
	except Exception as db_err:
		print(f"\n[ERROR] Failed to save telemetry in background: {db_err}", flush=True)
		return

	# Perform anomaly detection on a copy of the telemetry payload
	model_data = dict(payload_dict)
	model_data.pop("ac_status", None)
	model_data.pop("ac_thermostat", None)

	try:
		is_anom = service.is_anomaly(model_data)
		if is_anom:
			payload_dict["ac_status"] = ac_status
			payload_dict["ac_thermostat"] = ac_thermostat
			
			# Handle debouncing with threading.Timer
			with timer_lock:
				if alert_timer is None:
					print(f"\n[DEBOUNCER] Anomaly detected! Starting {ALERT_DELAY_SECONDS}s alert delay...", flush=True)
					alert_timer = threading.Timer(ALERT_DELAY_SECONDS, trigger_alert_action, [payload_dict])
					alert_timer.start()
				else:
					print("\n[DEBOUNCER] Anomaly detected, but alert timer is already running. Keeping original schedule.", flush=True)
		else:
			# If system is normal, cancel any pending alert timer
			with timer_lock:
				if alert_timer is not None:
					print("\n[DEBOUNCER] Telemetry is normal. Canceling pending anomaly alert!", flush=True)
					alert_timer.cancel()
					alert_timer = None
	except Exception as ml_err:
		print(f"\n[ERROR] Anomaly detection failed in background: {ml_err}", flush=True)


@app.post("/telemetry", status_code=201)
def receive_telemetry(payload: Telemetry, background_tasks: BackgroundTasks):
	payload_dict = payload.dict()
	background_tasks.add_task(process_telemetry_background, payload_dict)
	return {"status": "stored"}


def get_year_month_day(timestamp):
	if isinstance(timestamp, datetime):
		return timestamp.year, timestamp.month, timestamp.day
	elif isinstance(timestamp, str):
		try:
			dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
			return dt.year, dt.month, dt.day
		except Exception:
			return int(timestamp[:4]), int(timestamp[5:7]), int(timestamp[8:10])
	else:
		now = datetime.now(LOCAL_TZ)
		return now.year, now.month, now.day


@app.get("/telemetry")
def get_telemetry(start: Optional[str] = None, end: Optional[str] = None, ac_unit: Optional[str] = 'telemetry'):
	# Validate and normalize incoming date strings to SQLite 'YYYY-MM-DD HH:MM:SS'
	start_param = None
	end_param = None
	try:
		if start is not None:
			start_dt = datetime.fromisoformat(start)
			start_param = start_dt.strftime("%Y-%m-%d %H:%M:%S")
		if end is not None:
			end_dt = datetime.fromisoformat(end)
			end_param = end_dt.strftime("%Y-%m-%d %H:%M:%S")
	except Exception:
		raise HTTPException(status_code=400, detail="Invalid date format. Use ISO 8601.")

	conn = get_db_connection()
	cur = conn.cursor()
	if ac_unit == 'telemetry' or not ac_unit:
		query = "SELECT * FROM telemetry"
		clauses = []
		params = []
		if start_param is not None:
			clauses.append("timestamp >= %s")
			params.append(start_param)
		if end_param is not None:
			clauses.append("timestamp <= %s")
			params.append(end_param)
		if clauses:
			query += " WHERE " + " AND ".join(clauses)
		query += " ORDER BY id ASC"
	else:
		query = "SELECT * FROM data_gathered"
		clauses = ["ac_unit = %s"]
		params = [ac_unit]
		if start_param is not None:
			clauses.append("timestamp >= %s")
			params.append(start_param)
		if end_param is not None:
			clauses.append("timestamp <= %s")
			params.append(end_param)
		if clauses:
			query += " WHERE " + " AND ".join(clauses)
		query += " ORDER BY id ASC"
	cur.execute(query, params)
	rows = cur.fetchall()

	results = []
	if rows:
		ymd_pairs = set()
		for r in rows:
			ymd_pairs.add(get_year_month_day(r["timestamp"]))
		
		starts = {}
		for y, m, d in ymd_pairs:
			start_str = f"{y:04d}-{m:02d}-{d:02d} 00:00:00"
			if ac_unit == 'telemetry' or not ac_unit:
				cur.execute(
					"SELECT pzem_energy FROM telemetry WHERE timestamp >= %s ORDER BY timestamp ASC LIMIT 1",
					(start_str,)
				)
			else:
				cur.execute(
					"SELECT pzem_energy FROM data_gathered WHERE timestamp >= %s AND ac_unit = %s ORDER BY timestamp ASC LIMIT 1",
					(start_str, ac_unit)
				)
			start_row = cur.fetchone()
			starts[(y, m, d)] = start_row['pzem_energy'] if (start_row and start_row['pzem_energy'] is not None) else 0.0

		for r in rows:
			d_dict = dict(r)
			y, m, d = get_year_month_day(d_dict["timestamp"])
			e_start = starts.get((y, m, d), 0.0)
			if d_dict.get("pzem_energy") is not None:
				d_dict["pzem_energy"] = max(0.0, (d_dict["pzem_energy"] - e_start) / 1000.0)
			results.append(d_dict)
	conn.close()
	return results


@app.get("/telemetry/column")
def telemetry_column(column: Optional[str] = None, start: Optional[str] = None, end: Optional[str] = None, ac_unit: Optional[str] = 'telemetry'):
	# Return timestamp and the requested column values, optional ISO date range filter
	if not column:
 		raise HTTPException(status_code=400, detail="Missing 'column' query parameter")
		
	allowed = {
		"id", "timestamp", "dust_sensor", "dht_temp", "dht_humidity", "vibration",
		"ds18b20_temp1", "ds18b20_temp2", "pzem_voltage", "pzem_current",
		"pzem_power", "pzem_energy", "pzem_frequency", "pzem_power_factor",
		"ac_status", "ac_thermostat",
	}

	if column not in allowed:
		raise HTTPException(status_code=400, detail="Invalid column requested")

	start_param = None
	end_param = None
	try:
		if start is not None:
			start_dt = datetime.fromisoformat(start)
			start_param = start_dt.strftime("%Y-%m-%d %H:%M:%S")
		if end is not None:
			end_dt = datetime.fromisoformat(end)
			end_param = end_dt.strftime("%Y-%m-%d %H:%M:%S")
	except Exception:
		raise HTTPException(status_code=400, detail="Invalid date format. Use ISO 8601.")

	conn = get_db_connection()
	cur = conn.cursor()
	if ac_unit == 'telemetry' or not ac_unit:
		query = f"SELECT timestamp, {column} FROM telemetry"
		clauses = []
		params = []
		if start_param is not None:
			clauses.append("timestamp >= %s")
			params.append(start_param)
		if end_param is not None:
			clauses.append("timestamp <= %s")
			params.append(end_param)
		if clauses:
			query += " WHERE " + " AND ".join(clauses)
		query += " ORDER BY id ASC"
	else:
		query = f"SELECT timestamp, {column} FROM data_gathered"
		clauses = ["ac_unit = %s"]
		params = [ac_unit]
		if start_param is not None:
			clauses.append("timestamp >= %s")
			params.append(start_param)
		if end_param is not None:
			clauses.append("timestamp <= %s")
			params.append(end_param)
		if clauses:
			query += " WHERE " + " AND ".join(clauses)
		query += " ORDER BY id ASC"
	cur.execute(query, params)
	rows = cur.fetchall()

	results = []
	if rows:
		if column == "pzem_energy":
			ymd_pairs = set()
			for r in rows:
				ymd_pairs.add(get_year_month_day(r["timestamp"]))
			
			starts = {}
			for y, m, d in ymd_pairs:
				start_str = f"{y:04d}-{m:02d}-{d:02d} 00:00:00"
				if ac_unit == 'telemetry' or not ac_unit:
					cur.execute(
						"SELECT pzem_energy FROM telemetry WHERE timestamp >= %s ORDER BY timestamp ASC LIMIT 1",
						(start_str,)
					)
				else:
					cur.execute(
						"SELECT pzem_energy FROM data_gathered WHERE timestamp >= %s AND ac_unit = %s ORDER BY timestamp ASC LIMIT 1",
						(start_str, ac_unit)
					)
				start_row = cur.fetchone()
				starts[(y, m, d)] = start_row['pzem_energy'] if (start_row and start_row['pzem_energy'] is not None) else 0.0
			
			for r in rows:
				y, m, d = get_year_month_day(r["timestamp"])
				e_start = starts.get((y, m, d), 0.0)
				val = r[column]
				if val is not None:
					val = max(0.0, (val - e_start) / 1000.0)
				results.append({"timestamp": r["timestamp"], column: val})
		else:
			for r in rows:
				results.append({"timestamp": r["timestamp"], column: r[column]})
	conn.close()
	return results


@app.get("/telemetry/latest")
def latest_telemetry(ac_unit: Optional[str] = 'telemetry'):
	conn = get_db_connection()
	cur = conn.cursor()
	if ac_unit == 'telemetry' or not ac_unit:
		cur.execute("SELECT * FROM telemetry ORDER BY id DESC LIMIT 1")
	else:
		cur.execute("SELECT * FROM data_gathered WHERE ac_unit = %s ORDER BY id DESC LIMIT 1", (ac_unit,))
	row = cur.fetchone()
	if not row:
		conn.close()
		raise HTTPException(status_code=404, detail="No telemetry available")
	
	data = dict(row)
	ts = data.get("timestamp")
	y, m, d = get_year_month_day(ts)
	start_str = f"{y:04d}-{m:02d}-{d:02d} 00:00:00"
	if ac_unit == 'telemetry' or not ac_unit:
		cur.execute(
			"SELECT pzem_energy FROM telemetry WHERE timestamp >= %s ORDER BY timestamp ASC LIMIT 1",
			(start_str,)
		)
	else:
		cur.execute(
			"SELECT pzem_energy FROM data_gathered WHERE timestamp >= %s AND ac_unit = %s ORDER BY timestamp ASC LIMIT 1",
			(start_str, ac_unit)
		)
	start_row = cur.fetchone()
	conn.close()
	
	e_start = start_row['pzem_energy'] if (start_row and start_row['pzem_energy'] is not None) else 0.0
	if data.get("pzem_energy") is not None:
		data["pzem_energy"] = max(0.0, (data["pzem_energy"] - e_start) / 1000.0)
	return data


@app.get("/api/historical_data")
def get_historical_data(start: Optional[str] = None, end: Optional[str] = None):
	conn = get_db_connection()
	cur = conn.cursor()
	query = "SELECT * FROM historical_data"
	clauses = []
	params = []
	if start:
		clauses.append("date >= %s")
		params.append(start)
	if end:
		clauses.append("date <= %s")
		params.append(end)
	if clauses:
		query += " WHERE " + " AND ".join(clauses)
	query += " ORDER BY date ASC"
	cur.execute(query, params)
	rows = cur.fetchall()
	conn.close()

	result = []
	for r in rows:
		d = dict(r)
		if d.get("date") and not isinstance(d["date"], str):
			d["date"] = d["date"].strftime("%Y-%m-%d")
		result.append(d)
	return result


@app.get("/data_gathered")
def get_data_gathered(ac_unit: Optional[str] = None):
	conn = get_db_connection()
	cur = conn.cursor()
	if ac_unit:
		cur.execute("SELECT * FROM data_gathered WHERE ac_unit = %s ORDER BY timestamp DESC LIMIT 2000", (ac_unit,))
	else:
		cur.execute("SELECT * FROM data_gathered ORDER BY timestamp DESC LIMIT 2000")
	rows = cur.fetchall()

	results = []
	if rows:
		ymd_ac_pairs = set()
		for r in rows:
			y, m, d = get_year_month_day(r["timestamp"])
			ymd_ac_pairs.add((y, m, d, r["ac_unit"]))

		starts = {}
		for y, m, d, ac in ymd_ac_pairs:
			start_str = f"{y:04d}-{m:02d}-{d:02d} 00:00:00"
			cur.execute(
				"SELECT pzem_energy FROM data_gathered WHERE timestamp >= %s AND ac_unit = %s ORDER BY timestamp ASC LIMIT 1",
				(start_str, ac)
			)
			start_row = cur.fetchone()
			starts[(y, m, d, ac)] = start_row['pzem_energy'] if (start_row and start_row['pzem_energy'] is not None) else 0.0

		for r in rows:
			d_dict = dict(r)
			y, m, d = get_year_month_day(d_dict["timestamp"])
			ac = d_dict["ac_unit"]
			e_start = starts.get((y, m, d, ac), 0.0)
			if d_dict.get("pzem_energy") is not None:
				d_dict["pzem_energy"] = max(0.0, (d_dict["pzem_energy"] - e_start) / 1000.0)
			results.append(d_dict)
	conn.close()
	return results


@app.post("/data_gathered", status_code=201)
def save_data_gathered(payload: Telemetry):
	conn = get_db_connection()
	cur = conn.cursor()
	payload_dict = payload.dict()
	ac_unit = payload_dict.get("ac_unit") or "AC2"
	cur.execute(
		"""
		INSERT INTO data_gathered (
			timestamp, ac_unit,
			dust_sensor, dht_temp, dht_humidity, vibration,
			ds18b20_temp1, ds18b20_temp2,
			pzem_voltage, pzem_current, pzem_power, pzem_energy,
			pzem_frequency, pzem_power_factor,
			ac_status, ac_thermostat
		) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
		RETURNING id
		""",
		(
			datetime.now(LOCAL_TZ),
			ac_unit,
			payload_dict.get("dust_sensor"),
			payload_dict.get("dht_temp"),
			payload_dict.get("dht_humidity"),
			payload_dict.get("vibration"),
			payload_dict.get("ds18b20_temp1"),
			payload_dict.get("ds18b20_temp2"),
			payload_dict.get("pzem_voltage"),
			payload_dict.get("pzem_current"),
			payload_dict.get("pzem_power"),
			payload_dict.get("pzem_energy"),
			payload_dict.get("pzem_frequency"),
			payload_dict.get("pzem_power_factor"),
			payload_dict.get("ac_status"),
			payload_dict.get("ac_thermostat"),
		)
	)
	row_id = cur.fetchone()['id']
	conn.commit()
	conn.close()
	return {"status": "stored", "id": row_id}


@app.get("/ac_setup")
def read_ac_setup():
	return get_ac_setup()


@app.post("/ac_setup")
def set_ac_setup(payload: ACSetup):
	ac_values = get_ac_setup()
	ac_status = payload.ac_status if payload.ac_status is not None else ac_values.get("ac_status", "Not Set")
	ac_thermostat = payload.ac_thermostat if payload.ac_thermostat is not None else ac_values.get("ac_thermostat", "Not Set")
	data_gathering_mode = payload.data_gathering_mode if payload.data_gathering_mode is not None else ac_values.get("data_gathering_mode", "telemetry")
	data_gathering_unit = payload.data_gathering_unit if payload.data_gathering_unit is not None else ac_values.get("data_gathering_unit", "AC2")
	update_ac_setup(ac_status, ac_thermostat, data_gathering_mode, data_gathering_unit)
	return {
		"status": "updated",
		"ac_status": ac_status,
		"ac_thermostat": ac_thermostat,
		"data_gathering_mode": data_gathering_mode,
		"data_gathering_unit": data_gathering_unit
	}


def _delayed_shutdown() -> None:
	# Give the API response time to return before powering down.
	time.sleep(1)
	try:
		subprocess.run(["sudo", "shutdown", "-h", "now"], check=False)
	except Exception:
		# Fallback command if sudo is not configured for this runtime.
		os.system("shutdown -h now")


@app.post("/system/shutdown")
def shutdown_system():
	threading.Thread(target=_delayed_shutdown, daemon=True).start()
	return {"status": "accepted", "message": "Shutdown command sent."}

