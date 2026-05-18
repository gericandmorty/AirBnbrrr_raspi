from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import os
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


@app.post("/telemetry", status_code=201)
def receive_telemetry(payload: Telemetry):
	# Use AC setup values from the ac_setup table (single source of truth)
	ac_values = get_ac_setup()
	ac_status = ac_values.get("ac_status", "Not Set")
	ac_thermostat = ac_values.get("ac_thermostat", "Not Set")

	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute(
		"""
		INSERT INTO telemetry (
			dust_sensor, dht_temp, dht_humidity, vibration,
			ds18b20_temp1, ds18b20_temp2,
			pzem_voltage, pzem_current, pzem_power, pzem_energy,
			pzem_frequency, pzem_power_factor,
			ac_status, ac_thermostat
		) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
		RETURNING id
		""",
		(
			payload.dust_sensor,
			payload.dht_temp,
			payload.dht_humidity,
			payload.vibration,
			payload.ds18b20_temp1,
			payload.ds18b20_temp2,
			payload.pzem_voltage,
			payload.pzem_current,
			payload.pzem_power,
			payload.pzem_energy,
			payload.pzem_frequency,
			payload.pzem_power_factor,
			ac_status,
			ac_thermostat,
		),
	)
	row_id = cur.fetchone()['id']
	conn.commit()
	conn.close()
 
	payload_dict = payload.dict()
	payload_dict.pop("ac_status", None)
	payload_dict.pop("ac_thermostat", None)
	is_anom = service.is_anomaly(payload_dict)
	# print(f"\nPrediction result: Is anomaly? {is_anom}")
	if is_anom:
		payload_dict["ac_status"] = ac_status
		payload_dict["ac_thermostat"] = ac_thermostat
		process_anomaly(payload_dict)

	return {"id": row_id, "status": "stored"}


@app.get("/telemetry")
def get_telemetry(start: Optional[str] = None, end: Optional[str] = None):
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
	cur.execute(query, params)
	rows = cur.fetchall()
	conn.close()
	return [dict(r) for r in rows]


@app.get("/telemetry/column")
def telemetry_column(column: Optional[str] = None, start: Optional[str] = None, end: Optional[str] = None):
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
	# column name is safe to interpolate after validation against `allowed`
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
	cur.execute(query, params)
	rows = cur.fetchall()
	conn.close()
	return [{"timestamp": r["timestamp"], column: r[column]} for r in rows]


@app.get("/telemetry/latest")
def latest_telemetry():
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("SELECT * FROM telemetry ORDER BY id DESC LIMIT 1")
	row = cur.fetchone()
	conn.close()
	if not row:
		raise HTTPException(status_code=404, detail="No telemetry available")
	return dict(row)


@app.get("/ac_setup")
def read_ac_setup():
	return get_ac_setup()


@app.post("/ac_setup")
def set_ac_setup(payload: ACSetup):
	ac_status = payload.ac_status if payload.ac_status is not None else "Not Set"
	ac_thermostat = payload.ac_thermostat if payload.ac_thermostat is not None else "Not Set"
	update_ac_setup(ac_status, ac_thermostat)
	return {"status": "updated", "ac_status": ac_status, "ac_thermostat": ac_thermostat}


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

