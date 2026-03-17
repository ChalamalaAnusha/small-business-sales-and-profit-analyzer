import os
import re
import sqlite3


DB_FILE = os.environ.get("DB_FILE", "sales_profit_analyzer.db")


def _translate_query(query):
    translated = re.sub(
        r"CURDATE\(\)\s*-\s*INTERVAL\s+(\d+)\s+DAY",
        r"DATE('now', '-\1 day')",
        query,
        flags=re.IGNORECASE,
    )
    translated = re.sub(r"CURDATE\(\)", "DATE('now')", translated, flags=re.IGNORECASE)
    translated = translated.replace("%s", "?")
    return translated


class SQLiteCursorWrapper:
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, query, params=None):
        query = _translate_query(query)
        if params is None:
            return self._cursor.execute(query)
        return self._cursor.execute(query, params)

    def executemany(self, query, seq_of_params):
        query = _translate_query(query)
        return self._cursor.executemany(query, seq_of_params)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class SQLiteConnectionWrapper:
    def __init__(self, connection):
        self._connection = connection

    def cursor(self, *args, **kwargs):
        return SQLiteCursorWrapper(self._connection.cursor())

    def __enter__(self):
        self._connection.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._connection.__exit__(exc_type, exc_val, exc_tb)

    def __getattr__(self, name):
        return getattr(self._connection, name)


def get_connection():
    try:
        connection = sqlite3.connect(DB_FILE)
        connection.execute("PRAGMA foreign_keys = ON")
        return SQLiteConnectionWrapper(connection)
    except sqlite3.Error:
        return None


def init_database():
    connection = sqlite3.connect(DB_FILE)
    cursor = connection.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            email TEXT UNIQUE,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Detect whether legacy columns exist and rebuild users table when needed.
    cursor.execute("PRAGMA table_info(users)")
    user_columns = {row[1] for row in cursor.fetchall()}

    # Add new columns first if missing, then rebuild when legacy structure is detected.
    if "username" not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN username TEXT")
    if "email" not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN email TEXT")
    if "role" not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")

    cursor.execute("PRAGMA table_info(users)")
    user_columns = {row[1] for row in cursor.fetchall()}
    needs_users_rebuild = "name" in user_columns

    if needs_users_rebuild:
        username_candidates = []
        if "username" in user_columns:
            username_candidates.append("NULLIF(TRIM(username), '')")
        if "email" in user_columns:
            username_candidates.append(
                "CASE WHEN email IS NOT NULL AND INSTR(email, '@') > 1 THEN LOWER(SUBSTR(email, 1, INSTR(email, '@') - 1)) END"
            )
        if "name" in user_columns:
            username_candidates.append("CASE WHEN name IS NOT NULL THEN LOWER(REPLACE(TRIM(name), ' ', '_')) END")

        username_expr = "COALESCE(" + ", ".join(username_candidates + ["'user_' || id"]) + ")"
        role_expr = (
            "CASE WHEN LOWER(TRIM(role)) = 'admin' THEN 'admin' ELSE 'user' END"
            if "role" in user_columns
            else "'user'"
        )
        email_expr = "LOWER(NULLIF(TRIM(email), ''))" if "email" in user_columns else "NULL"
        created_at_expr = "COALESCE(created_at, CURRENT_TIMESTAMP)" if "created_at" in user_columns else "CURRENT_TIMESTAMP"

        cursor.execute("PRAGMA foreign_keys = OFF")
        cursor.execute(
            """
            CREATE TABLE users_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE,
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            f"""
            INSERT INTO users_new (id, username, email, password, role, created_at)
            SELECT
                id,
                {username_expr} AS username,
                {email_expr} AS email,
                password,
                {role_expr} AS role,
                {created_at_expr} AS created_at
            FROM users
            """
        )

        cursor.execute("DROP TABLE users")
        cursor.execute("ALTER TABLE users_new RENAME TO users")
        cursor.execute("PRAGMA foreign_keys = ON")

    # Guarantee every user has a unique fallback username.
    cursor.execute("SELECT id FROM users WHERE username IS NULL OR TRIM(username) = ''")
    missing_username_rows = cursor.fetchall()
    for (user_id,) in missing_username_rows:
        cursor.execute("UPDATE users SET username=? WHERE id=?", (f"user_{user_id}", user_id))

    # Resolve potential duplicate usernames before enforcing uniqueness.
    cursor.execute(
        """
        SELECT username
        FROM users
        GROUP BY username
        HAVING COUNT(*) > 1
        """
    )
    duplicate_usernames = cursor.fetchall()
    for (duplicate_username,) in duplicate_usernames:
        cursor.execute(
            "SELECT id FROM users WHERE username=? ORDER BY id ASC",
            (duplicate_username,),
        )
        duplicate_rows = cursor.fetchall()
        for (user_id,) in duplicate_rows[1:]:
            cursor.execute("UPDATE users SET username=? WHERE id=?", (f"{duplicate_username}_{user_id}", user_id))

    cursor.execute("UPDATE users SET role='user' WHERE role IS NULL OR TRIM(role) = ''")
    cursor.execute("UPDATE users SET email=LOWER(TRIM(email)) WHERE email IS NOT NULL")
    cursor.execute("UPDATE users SET email=NULL WHERE email IS NOT NULL AND TRIM(email) = ''")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username)")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS businesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER,
            type TEXT CHECK(type IN ('Sale', 'Expense')),
            category TEXT,
            amount REAL,
            txn_date TEXT,
            notes TEXT,
            FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER,
            name TEXT,
            cost_price REAL,
            sale_price REAL,
            stock INTEGER,
            FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER,
            report_type TEXT,
            file_url TEXT,
            generated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE
        )
        """
    )

    connection.commit()
    connection.close()