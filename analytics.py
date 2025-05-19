import os
import sqlite3
from datetime import datetime

# Path to analytics SQLite database (ensure the 'instance' directory exists)
DB_PATH = os.getenv('ANALYTICS_DB_PATH', 'instance/analytics.db')

def init_analytics_db():
    """
    Initialize the analytics database with tables for logins and recommendations.
    """
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Create logins table
    c.execute('''
        CREATE TABLE IF NOT EXISTS logins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            service TEXT NOT NULL,
            token TEXT NOT NULL
        )
    ''')
    
    # Create recommendations table with language field
    c.execute('''
        CREATE TABLE IF NOT EXISTS recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            timestamp TEXT NOT NULL,
            service TEXT NOT NULL,
            playlist_id TEXT NOT NULL,
            recommendation TEXT,
            details TEXT,
            language TEXT,
            outcome TEXT DEFAULT 'success',
            error_message TEXT
        )
    ''')
    
    # Check if language column exists, add it if not
    try:
        c.execute("SELECT language FROM recommendations LIMIT 1")
    except sqlite3.OperationalError:
        # Column doesn't exist, add it
        c.execute("ALTER TABLE recommendations ADD COLUMN language TEXT")
        
    # Check if outcome column exists, add it if not
    try:
        c.execute("SELECT outcome FROM recommendations LIMIT 1")
    except sqlite3.OperationalError:
        # Column doesn't exist, add it
        c.execute("ALTER TABLE recommendations ADD COLUMN outcome TEXT DEFAULT 'success'")
        
    # Check if error_message column exists, add it if not
    try:
        c.execute("SELECT error_message FROM recommendations LIMIT 1")
    except sqlite3.OperationalError:
        # Column doesn't exist, add it
        c.execute("ALTER TABLE recommendations ADD COLUMN error_message TEXT")
    
    conn.commit()
    conn.close()

def store_login_data(service: str, token: dict) -> None:
    """
    Record a login event for the given service, storing the raw token info.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        'INSERT INTO logins (timestamp, service, token) VALUES (?, ?, ?)',
        (datetime.utcnow().isoformat(), service, repr(token))
    )
    conn.commit()
    conn.close()

def update_recommendation_data(
    session_id: str,
    service: str,
    playlist_id: str,
    recommendation: str = None,
    details: dict = None,
    language: str = None,
    outcome: str = 'success',
    error_message: str = None
) -> None:
    """
    Record a recommendation event, including session, playlist, output, and metadata.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        '''INSERT INTO recommendations
           (session_id, timestamp, service, playlist_id, recommendation, details, language, outcome, error_message)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (
            session_id,
            datetime.utcnow().isoformat(),
            service,
            playlist_id,
            recommendation,
            repr(details) if details else None,
            language,
            outcome,
            error_message
        )
    )
    conn.commit()
    conn.close()
