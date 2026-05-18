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
    Saves it to the admin table for the given username.
    """
    token = secrets.token_hex(32)
    # Store with explicit UTC timezone
    expiry = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE admin SET access_token = %s, access_token_expiry = %s WHERE username = %s",
        (token, expiry, username)
    )
    conn.commit()
    conn.close()
    return token, expiry

def clear_session(token: str) -> None:
    """Invalidates the session token in the database."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE admin SET access_token = NULL, access_token_expiry = NULL WHERE access_token = %s",
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
    cur.execute(
        "SELECT id, username, access_token_expiry FROM admin WHERE access_token = %s",
        (token,)
    )
    row = cur.fetchone()
    conn.close()
    
    if not row:
        return None
        
    try:
        expiry_str = row["access_token_expiry"]
        if not expiry_str:
            return None
        expiry = datetime.fromisoformat(expiry_str)
        # Handle timezone compatibility
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
            
        if datetime.now(timezone.utc) > expiry:
            # Token is expired
            return None
    except Exception:
        return None
        
    return dict(row)
