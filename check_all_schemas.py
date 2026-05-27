from database import get_db_connection

TABLES = ['telemetry', 'alerts', 'contacts', 'ac_setup']

conn = get_db_connection()
cur = conn.cursor()

for table in TABLES:
    cur.execute(
        "SELECT column_name, column_default, data_type FROM information_schema.columns "
        "WHERE table_name = %s ORDER BY ordinal_position",
        (table,)
    )
    rows = cur.fetchall()
    print(f"\n=== {table} ===")
    for r in rows:
        print(f"  {r['column_name']:20} | default={r['column_default']} | type={r['data_type']}")

conn.close()
