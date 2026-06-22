import bcrypt
import secrets
from datetime import datetime, timedelta, timezone
from database import get_db_connection

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a raw password against its bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

def generate_session(username: str) -> tuple[str, str]:
    """
    Generates a secure 32-byte token and a 24-hour expiry ISO timestamp.
    Saves it to the admin_sessions table to allow multiple active sessions per user.
    """
    token = secrets.token_hex(32)
    # Store with explicit UTC timezone
    expiry = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Optional cleanup: remove expired sessions for this user
    try:
        cur.execute(
            "DELETE FROM admin_sessions WHERE username = %s AND access_token_expiry < %s",
            (username, datetime.now(timezone.utc).isoformat())
        )
    except Exception:
        pass

    cur.execute(
        "INSERT INTO admin_sessions (username, access_token, access_token_expiry) VALUES (%s, %s, %s)",
        (username, token, expiry)
    )
    conn.commit()
    conn.close()
    return token, expiry

def clear_session(token: str) -> None:
    """Invalidates the session token in the database."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM admin_sessions WHERE access_token = %s",
        (token,)
    )
    conn.commit()
    conn.close()

def get_admin_from_token(token: str) -> dict | None:
    """
    Checks if a token is valid and not expired.
    Returns the admin record dict or None if invalid.
    """
    if not token:
        return None
        
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Check if session exists
    cur.execute(
        "SELECT username, access_token_expiry FROM admin_sessions WHERE access_token = %s",
        (token,)
    )
    session_row = cur.fetchone()
    
    if not session_row:
        conn.close()
        return None
        
    try:
        expiry_str = session_row["access_token_expiry"]
        if not expiry_str:
            conn.close()
            return None
        expiry = datetime.fromisoformat(expiry_str)
        # Handle timezone compatibility
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
            
        if datetime.now(timezone.utc) > expiry:
            # Token is expired, clean it up
            cur.execute("DELETE FROM admin_sessions WHERE access_token = %s", (token,))
            conn.commit()
            conn.close()
            return None
    except Exception:
        conn.close()
        return None
        
    # Session is valid. Get admin details from admin table
    cur.execute(
        "SELECT id, username FROM admin WHERE username = %s",
        (session_row["username"],)
    )
    admin_row = cur.fetchone()
    conn.close()
    
    if not admin_row:
        return None
        
    return {
        "id": admin_row["id"],
        "username": admin_row["username"],
        "access_token_expiry": session_row["access_token_expiry"]
    }
