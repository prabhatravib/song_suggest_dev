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
    c.execute('''
        CREATE TABLE IF NOT EXISTS logins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            service TEXT NOT NULL,
            token TEXT NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            timestamp TEXT NOT NULL,
            service TEXT NOT NULL,
            playlist_id TEXT NOT NULL,
            recommendation TEXT,
            details TEXT
        )
    ''')
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
    recommendation: str,
    details: dict
) -> None:
    """
    Record a recommendation event, including session, playlist, output, and metadata.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        '''INSERT INTO recommendations
           (session_id, timestamp, service, playlist_id, recommendation, details)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (
            session_id,
            datetime.utcnow().isoformat(),
            service,
            playlist_id,
            recommendation,
            repr(details)
        )
    )
    conn.commit()
    conn.close()
