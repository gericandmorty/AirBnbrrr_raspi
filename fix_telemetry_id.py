from database import get_db_connection
conn = get_db_connection()
cur = conn.cursor()
cur.execute("CREATE SEQUENCE IF NOT EXISTS telemetry_id_seq")
cur.execute("SELECT setval('telemetry_id_seq', COALESCE((SELECT MAX(id) FROM telemetry), 0) + 1, false)")
cur.execute("ALTER TABLE telemetry ALTER COLUMN id SET DEFAULT nextval('telemetry_id_seq')")
conn.commit()
conn.close()
print("Done - telemetry.id now has auto-increment default.")
