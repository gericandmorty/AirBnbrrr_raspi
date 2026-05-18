from database import get_db_connection

def get_ac_setup():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT ac_status, ac_thermostat FROM ac_setup LIMIT 1")
    row = cur.fetchone()
    conn.close()
    if not row:
        return {"ac_status": "Not Set", "ac_thermostat": "Not Set"}
    return {"ac_status": row["ac_status"], "ac_thermostat": row["ac_thermostat"]}

def update_ac_setup(ac_status: str, ac_thermostat: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE ac_setup SET ac_status = %s, ac_thermostat = %s", (ac_status, ac_thermostat))
    conn.commit()
    conn.close()
