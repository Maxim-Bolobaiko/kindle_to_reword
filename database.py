import logging
import sqlite3

logger = logging.getLogger(__name__)
DB_NAME = "user_history.db"


def init_db():
    """Initializes the SQLite database with the history table."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS history (
            user_id INTEGER,
            word TEXT,
            UNIQUE(user_id, word)
        )
    """
    )
    conn.commit()
    conn.close()


def get_user_history(user_id):
    """Returns a set of words already processed for the user."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT word FROM history WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return {row[0] for row in rows}


def add_words_to_history(user_id, words):
    """Bulk adds new words to the user's history."""
    if not words:
        return
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        data = [(user_id, w.lower()) for w in words]
        cursor.executemany(
            "INSERT OR IGNORE INTO history (user_id, word) VALUES (?, ?)", data
        )
        conn.commit()
    except Exception as e:
        logger.error(f"DB Error: {e}")
    finally:
        conn.close()


# Initialize DB on import
init_db()
