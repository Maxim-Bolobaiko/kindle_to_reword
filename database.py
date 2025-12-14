import logging
import sqlite3

from config import DB_FILE

logger = logging.getLogger(__name__)


def init_db():
    """Initializes the database tables."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            # Table to store user history: who, what word, when
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS user_words (
                    user_id INTEGER,
                    word TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, word)
                )
            """
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")


def get_user_history(user_id):
    """Returns a set of words previously processed by the user."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT word FROM user_words WHERE user_id = ?", (user_id,))
            return set(row[0] for row in cursor.fetchall())
    except Exception as e:
        logger.error(f"Failed to get user history: {e}")
        return set()


def add_words_to_history(user_id, words_list):
    """Bulk adds new words to the user's history."""
    if not words_list:
        return
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            # Convert to lowercase for consistency
            data = [(user_id, w.lower()) for w in words_list]
            # INSERT OR IGNORE skips duplicates automatically
            cursor.executemany(
                "INSERT OR IGNORE INTO user_words (user_id, word) VALUES (?, ?)", data
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to add words to history: {e}")


# Initialize DB on module import
init_db()
