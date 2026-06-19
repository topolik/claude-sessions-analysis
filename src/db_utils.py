import sqlite3


def table_and_cols_exist(conn, table, cols):
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    if not cursor.fetchone():
        return False
    cursor.execute(f"PRAGMA table_info([{table}])")
    existing = {col[1] for col in cursor.fetchall()}
    return all(c in existing for c in cols)
