import psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path
import os

# Get the directory where database.py is located
BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"

DB_URI = None

# 1. Prioritize OS environment variables first (critical for Docker/Render deployments!)
DB_URI = os.environ.get("SUPABASE_URL")

# 2. Try to read from local .env file next
if not DB_URI and ENV_FILE.exists():
    with open(ENV_FILE, "r") as f:
        for line in f:
            cleaned_line = line.strip()
            # Ignore comments and empty lines
            if not cleaned_line or cleaned_line.startswith("#"):
                continue
            if "=" in cleaned_line:
                key, val = cleaned_line.split("=", 1)
                if key.strip() == "SUPABASE_URL":
                    DB_URI = val.strip()
                    break

# 2. Fallback to supabase_connection.txt if .env doesn't specify it
if not DB_URI:
    CONNECTION_FILE = BASE_DIR / "supabase_connection.txt"
    if CONNECTION_FILE.exists():
        with open(CONNECTION_FILE, "r") as f:
            DB_URI = f.read().strip()

if not DB_URI:
    raise ValueError("Database connection string not found. Please define SUPABASE_URL in .env or create supabase_connection.txt")

def get_db_connection():
    """
    Establish and return a connection to the PostgreSQL database.
    We use RealDictCursor so rows behave similarly to sqlite3.Row (accessible by dictionary keys).
    """
    conn = psycopg2.connect(DB_URI)
    conn.cursor_factory = RealDictCursor
    return conn
