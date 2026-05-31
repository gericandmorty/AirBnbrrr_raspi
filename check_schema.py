from database import get_db_connection
conn = get_db_connection()
cur = conn.cursor()
cur.execute(
    "SELECT column_name, column_default, data_type FROM information_schema.columns "
    "WHERE table_name = 'alerts' ORDER BY ordinal_position"
)
rows = cur.fetchall()
for r in rows:
    print(dict(r))
conn.close()
