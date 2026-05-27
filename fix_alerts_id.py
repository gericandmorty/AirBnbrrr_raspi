from database import get_db_connection
conn = get_db_connection()
cur = conn.cursor()

# Create a sequence and attach it to the id column
cur.execute("CREATE SEQUENCE IF NOT EXISTS alerts_id_seq")
cur.execute("SELECT setval('alerts_id_seq', COALESCE((SELECT MAX(id) FROM alerts), 0) + 1, false)")
cur.execute("ALTER TABLE alerts ALTER COLUMN id SET DEFAULT nextval('alerts_id_seq')")
conn.commit()
conn.close()
print("Done — alerts.id now has auto-increment default.")
