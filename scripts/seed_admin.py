#!/usr/bin/env python3
import sys
from pathlib import Path

# Add the parent directory of this script to the Python path
# so we can import from database and services
sys.path.append(str(Path(__file__).resolve().parent.parent))

from database import get_db_connection
from services.auth import hash_password

def seed_admin():
    print("Connecting to Supabase database...")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        return

    try:
        # Check if admin table exists and if the user 'admin' is already there
        cur.execute("SELECT id FROM admin WHERE username = %s", ("admin",))
        if cur.fetchone():
            print("Admin account 'admin' already exists. Skipping seeding.")
            conn.close()
            return
            
        print("Hashing password 'admin123' using bcrypt...")
        hashed_password = hash_password("admin123")
        
        print("Seeding admin account...")
        cur.execute(
            "INSERT INTO admin (username, password) VALUES (%s, %s)",
            ("admin", hashed_password)
        )
        conn.commit()
        print("Admin account seeded successfully!")
    except Exception as e:
        print(f"An error occurred during seeding: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    seed_admin()
