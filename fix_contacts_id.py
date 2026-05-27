from database import get_db_connection

conn = get_db_connection()
cur = conn.cursor()
cur.execute("CREATE SEQUENCE IF NOT EXISTS contacts_id_seq")
cur.execute("SELECT setval('contacts_id_seq', COALESCE((SELECT MAX(id) FROM contacts), 0) + 1, false)")
cur.execute("ALTER TABLE contacts ALTER COLUMN id SET DEFAULT nextval('contacts_id_seq')")
conn.commit()
conn.close()
print("Done - contacts.id now has auto-increment default.")
