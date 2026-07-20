#!/usr/bin/env python3
import sys
from pathlib import Path

# Add the parent directory of this script to the Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from database import get_db_connection

def clear_alerts():
    print("Connecting to the database...")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        return

    try:
        print("Truncating 'alerts' table and resetting IDs...")
        cur.execute("TRUNCATE TABLE alerts RESTART IDENTITY")
        conn.commit()
        print("All alert data deleted successfully!")
    except Exception as e:
        print(f"An error occurred: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    clear_alerts()
