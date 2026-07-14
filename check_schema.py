from database import get_db_connection
conn = get_db_connection()
cur = conn.cursor()
cur.execute(
    "SELECT table_name, column_name, column_default, data_type "
    "FROM information_schema.columns "
    "WHERE table_schema = 'public' "
    "ORDER BY table_name, ordinal_position"
)
rows = cur.fetchall()
tables = {}
for r in rows:
    tbl = r["table_name"]
    if tbl not in tables:
        tables[tbl] = []
    tables[tbl].append(f"{r['column_name']} ({r['data_type']})")
for tbl, cols in tables.items():
    print(f"Table {tbl}: {', '.join(cols)}")
conn.close()

