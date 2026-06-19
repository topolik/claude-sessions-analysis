import argparse
from datetime import datetime
import hashlib
import os
import sqlite3
import glob
import json

_known_columns = {}

def ensure_columns_exist(cursor, table_name, col_names):
    if table_name not in _known_columns:
        cursor.execute(f"PRAGMA table_info({table_name})")
        _known_columns[table_name] = {col[1] for col in cursor.fetchall()}
        
    for col in col_names:
        if col not in _known_columns[table_name]:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN [{col}] TEXT")
            _known_columns[table_name].add(col)

def setup_database(conn):
    cursor = conn.cursor()

    # Clear cached columns for a clean run
    _known_columns.clear()

    # 1. Sessions Table (session_id is file-path MD5, native_session_id is the parsed sessionId)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        file_path TEXT UNIQUE,
        native_session_id TEXT
    );
    """)

    # 2. Events Table (preserving file line order via row_id AUTOINCREMENT, NO raw_json column!)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS events (
        row_id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        event_id TEXT,
        timestamp TEXT,
        event_type TEXT,
        role TEXT,
        input_tokens INTEGER DEFAULT 0,
        output_tokens INTEGER DEFAULT 0,
        cache_read_tokens INTEGER DEFAULT 0,
        cache_creation_tokens INTEGER DEFAULT 0,
        FOREIGN KEY(session_id) REFERENCES sessions(session_id)
    );
    """)

    # 3. Normalized Messages Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        message_id TEXT,
        event_row_id INTEGER,
        content TEXT,
        PRIMARY KEY (event_row_id, message_id),
        FOREIGN KEY(event_row_id) REFERENCES events(row_id)
    );
    """)

    # 4. Normalized Tool Calls Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tool_calls (
        tool_use_id TEXT,
        event_row_id INTEGER,
        part_index INTEGER,
        tool_name TEXT,
        input_json TEXT,
        PRIMARY KEY (event_row_id, tool_use_id),
        FOREIGN KEY(event_row_id) REFERENCES events(row_id)
    );
    """)

    # 5. Normalized Tool Results Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tool_results (
        tool_use_id TEXT,
        event_row_id INTEGER,
        part_index INTEGER,
        output_content TEXT,
        is_error INTEGER,
        content_json TEXT,
        PRIMARY KEY (event_row_id, tool_use_id),
        FOREIGN KEY(event_row_id) REFERENCES events(row_id)
    );
    """)

    # 6. Attachments Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS attachments (
        event_row_id INTEGER PRIMARY KEY,
        FOREIGN KEY(event_row_id) REFERENCES events(row_id)
    );
    """)

    # 7. Message Parts Table (for other part types like thinking, signature)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS message_parts (
        row_id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_row_id INTEGER,
        part_index INTEGER,
        part_type TEXT,
        FOREIGN KEY(event_row_id) REFERENCES events(row_id)
    );
    """)

    # Performance Indices
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_event ON messages(event_row_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tool_calls_event ON tool_calls(event_row_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tool_results_event ON tool_results(event_row_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_attachments_event ON attachments(event_row_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_message_parts_event ON message_parts(event_row_id);")
    conn.commit()

def ingest_files(since=None):
    db_path = os.path.join("output", "claude_sessions.db")
    os.makedirs("output", exist_ok=True)

    if since is None:
        # Full rebuild: nuke and re-create
        if os.path.exists(db_path):
            os.remove(db_path)
            print(f"Removed existing database: {db_path}")
    else:
        if not os.path.exists(db_path):
            print(f"No existing database found. Running full ingestion instead.")
            since = None

    conn = sqlite3.connect(db_path)
    setup_database(conn)
    cursor = conn.cursor()

    # Find all JSONL files recursively
    file_pattern = os.path.join("projects", "**", "*.jsonl")
    jsonl_files = glob.glob(file_pattern, recursive=True)

    if since is not None:
        cutoff = since.timestamp()
        jsonl_files = [f for f in jsonl_files if os.path.getmtime(f) >= cutoff]
        print(f"Found {len(jsonl_files)} session log files modified since {since.isoformat()}.")
    else:
        print(f"Found {len(jsonl_files)} session log files to ingest.")

    registered_sessions = set()
    total_rows_inserted = 0

    for file_idx, file_path in enumerate(jsonl_files, 1):
        # 1. Generate unique file-level session_id
        session_id = hashlib.md5(file_path.encode('utf-8')).hexdigest()

        # In incremental mode, purge old data for this session before re-ingesting
        if since is not None:
            cursor.execute("SELECT row_id FROM events WHERE session_id = ?", (session_id,))
            old_row_ids = [r[0] for r in cursor.fetchall()]
            if old_row_ids:
                placeholders = ','.join(['?'] * len(old_row_ids))
                for child_table in ('messages', 'tool_calls', 'tool_results', 'attachments', 'message_parts'):
                    cursor.execute(f"DELETE FROM {child_table} WHERE event_row_id IN ({placeholders})", old_row_ids)
                cursor.execute(f"DELETE FROM events WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))

        # 2. Scan the file for any native sessionId
        native_session_id = None
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        if isinstance(data, dict) and 'sessionId' in data:
                            native_session_id = data['sessionId']
                            break
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"Error scanning {file_path}: {e}")
            continue

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if not line.strip():
                        continue
                    
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError as jde:
                        print(f"Warning: JSON decode error in {file_path}: {jde}")
                        continue

                    if session_id not in registered_sessions:
                        cursor.execute("""
                        INSERT OR IGNORE INTO sessions (session_id, file_path, native_session_id) 
                        VALUES (?, ?, ?)
                        """, (session_id, file_path, native_session_id))
                        registered_sessions.add(session_id)

                    # Extract event parameters
                    event_id = data.get('uuid') or data.get('messageId')
                    timestamp = data.get('timestamp')
                    event_type = data.get('type')
                    role = None
                    input_tokens = 0
                    output_tokens = 0
                    cache_read = 0
                    cache_create = 0

                    msg_data = data.get('message')
                    if isinstance(msg_data, dict):
                        role = msg_data.get('role')
                        usage = msg_data.get('usage') or {}
                        if isinstance(usage, dict):
                            input_tokens = usage.get('input_tokens', 0)
                            output_tokens = usage.get('output_tokens', 0)
                            cache_read = usage.get('cache_read_input_tokens', 0)
                            cache_create = usage.get('cache_creation_input_tokens', 0)

                    # Build fields dictionary dynamically for the events table
                    event_fields = {
                        'session_id': session_id,
                        'event_id': event_id,
                        'timestamp': timestamp,
                        'event_type': event_type,
                        'role': role,
                        'input_tokens': input_tokens,
                        'output_tokens': output_tokens,
                        'cache_read_tokens': cache_read,
                        'cache_creation_tokens': cache_create
                    }

                    # Add auxiliary root-level keys
                    for k, v in data.items():
                        if k not in ('uuid', 'messageId', 'timestamp', 'type', 'sessionId', 'message'):
                            if k == 'content' and event_type == 'system':
                                continue
                            if isinstance(v, (list, dict)):
                                event_fields[k] = json.dumps(v)
                            else:
                                event_fields[k] = v

                    # Add auxiliary usage fields
                    if isinstance(msg_data, dict):
                        usage = msg_data.get('usage') or {}
                        if isinstance(usage, dict):
                            for k, v in usage.items():
                                if k not in ('input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens'):
                                    col_name = f"usage_{k}"
                                    if isinstance(v, (list, dict)):
                                        event_fields[col_name] = json.dumps(v)
                                    else:
                                        event_fields[col_name] = v

                    # Insert core & auxiliary event fields dynamically into first-class columns
                    ensure_columns_exist(cursor, 'events', event_fields.keys())
                    e_columns = list(event_fields.keys())
                    e_placeholders = ', '.join(['?'] * len(e_columns))
                    safe_e_columns = [f"[{col}]" for col in e_columns]
                    e_sql = f"INSERT INTO events ({', '.join(safe_e_columns)}) VALUES ({e_placeholders})"
                    cursor.execute(e_sql, list(event_fields.values()))

                    event_row_id = cursor.lastrowid
                    total_rows_inserted += 1

                    # Parse message/tool contents for query structured tables
                    if isinstance(msg_data, dict):
                        message_fields = {
                            'message_id': event_id or f"msg_{event_row_id}",
                            'event_row_id': event_row_id,
                            'content': msg_data.get('content') if isinstance(msg_data.get('content'), str) else None
                        }

                        # Store auxiliary message-level metadata columns if they exist
                        for k, v in msg_data.items():
                            if k not in ('role', 'usage', 'content'):
                                if isinstance(v, (list, dict)):
                                    message_fields[k] = json.dumps(v)
                                else:
                                    message_fields[k] = v

                        # Insert into messages table
                        ensure_columns_exist(cursor, 'messages', message_fields.keys())
                        m_columns = list(message_fields.keys())
                        m_placeholders = ', '.join(['?'] * len(m_columns))
                        safe_m_columns = [f"[{col}]" for col in m_columns]
                        m_sql = f"INSERT OR REPLACE INTO messages ({', '.join(safe_m_columns)}) VALUES ({m_placeholders})"
                        cursor.execute(m_sql, list(message_fields.values()))

                        content = msg_data.get('content')
                        if isinstance(content, list):
                            for i, part in enumerate(content):
                                if not isinstance(part, dict):
                                    continue
                                part_type = part.get('type')
                                if part_type == 'text':
                                    text = part.get('text', '')
                                    message_id = f"msg_{event_row_id}_{i}"
                                    cursor.execute("INSERT OR REPLACE INTO messages (message_id, event_row_id, content) VALUES (?, ?, ?)", (message_id, event_row_id, text))
                                elif part_type == 'tool_use':
                                    tool_use_id = part.get('id')
                                    tool_name = part.get('name')
                                    tool_input = json.dumps(part.get('input', {}))

                                    tool_call_fields = {
                                        'tool_use_id': tool_use_id,
                                        'event_row_id': event_row_id,
                                        'part_index': i,
                                        'tool_name': tool_name,
                                        'input_json': tool_input
                                    }

                                    # Add other tool_use auxiliary keys
                                    for pk, pv in part.items():
                                        if pk not in ('type', 'id', 'name', 'input'):
                                            if isinstance(pv, (list, dict)):
                                                tool_call_fields[pk] = json.dumps(pv)
                                            else:
                                                tool_call_fields[pk] = pv

                                    ensure_columns_exist(cursor, 'tool_calls', tool_call_fields.keys())
                                    tc_columns = list(tool_call_fields.keys())
                                    tc_placeholders = ', '.join(['?'] * len(tc_columns))
                                    safe_tc_columns = [f"[{col}]" for col in tc_columns]
                                    tc_sql = f"INSERT OR REPLACE INTO tool_calls ({', '.join(safe_tc_columns)}) VALUES ({tc_placeholders})"
                                    cursor.execute(tc_sql, list(tool_call_fields.values()))

                                elif part_type == 'tool_result':
                                    tool_use_id = part.get('tool_use_id')
                                    tool_output = part.get('content', '')
                                    if isinstance(tool_output, list):
                                        tool_output_str = ""
                                        for subpart in tool_output:
                                            if isinstance(subpart, dict) and 'text' in subpart:
                                                tool_output_str += subpart.get('text', '')
                                        tool_output = tool_output_str
                                    is_error = 1 if part.get('is_error') else 0

                                    tool_result_fields = {
                                        'tool_use_id': tool_use_id,
                                        'event_row_id': event_row_id,
                                        'part_index': i,
                                        'output_content': tool_output,
                                        'is_error': is_error,
                                        'content_json': json.dumps(part.get('content', ''))
                                    }

                                    # Add other tool_result auxiliary keys
                                    for pk, pv in part.items():
                                        if pk not in ('type', 'tool_use_id', 'is_error', 'content'):
                                            if isinstance(pv, (list, dict)):
                                                tool_result_fields[pk] = json.dumps(pv)
                                            else:
                                                tool_result_fields[pk] = pv

                                    ensure_columns_exist(cursor, 'tool_results', tool_result_fields.keys())
                                    tr_columns = list(tool_result_fields.keys())
                                    tr_placeholders = ', '.join(['?'] * len(tr_columns))
                                    safe_tr_columns = [f"[{col}]" for col in tr_columns]
                                    tr_sql = f"INSERT OR REPLACE INTO tool_results ({', '.join(safe_tr_columns)}) VALUES ({tr_placeholders})"
                                    cursor.execute(tr_sql, list(tool_result_fields.values()))

                                else:
                                    # For other part types (e.g. thinking, signature), store in message_parts table
                                    part_fields = {
                                        'event_row_id': event_row_id,
                                        'part_index': i,
                                        'part_type': part_type
                                    }
                                    for pk, pv in part.items():
                                        if pk != 'type':
                                            if isinstance(pv, (list, dict)):
                                                part_fields[pk] = json.dumps(pv)
                                            else:
                                                part_fields[pk] = pv

                                    ensure_columns_exist(cursor, 'message_parts', part_fields.keys())
                                    mp_columns = list(part_fields.keys())
                                    mp_placeholders = ', '.join(['?'] * len(mp_columns))
                                    safe_mp_columns = [f"[{col}]" for col in mp_columns]
                                    mp_sql = f"INSERT OR REPLACE INTO message_parts ({', '.join(safe_mp_columns)}) VALUES ({mp_placeholders})"
                                    cursor.execute(mp_sql, list(part_fields.values()))

                    elif event_type == 'system' and data.get('content'):
                        message_id = f"sys_{event_row_id}"
                        cursor.execute("INSERT OR REPLACE INTO messages (message_id, event_row_id, content) VALUES (?, ?, ?)", (message_id, event_row_id, data.get('content')))

                    # Store attachments in attachments table for any event containing an attachment
                    if data.get('attachment'):
                        attachment = data.get('attachment')
                        if isinstance(attachment, dict):
                            attachment_fields = {
                                'event_row_id': event_row_id
                            }
                            for k, v in attachment.items():
                                if isinstance(v, (list, dict)):
                                    attachment_fields[k] = json.dumps(v)
                                else:
                                    attachment_fields[k] = v

                            ensure_columns_exist(cursor, 'attachments', attachment_fields.keys())
                            a_columns = list(attachment_fields.keys())
                            a_placeholders = ', '.join(['?'] * len(a_columns))
                            safe_a_columns = [f"[{col}]" for col in a_columns]
                            a_sql = f"INSERT OR REPLACE INTO attachments ({', '.join(safe_a_columns)}) VALUES ({a_placeholders})"
                            cursor.execute(a_sql, list(attachment_fields.values()))

        except Exception as e:
            print(f"Error reading file {file_path}: {e}")

        # Commit periodically (every 10 files) to boost efficiency and safety
        if file_idx % 10 == 0:
            conn.commit()
            print(f"Ingested {file_idx}/{len(jsonl_files)} files. Inserted {total_rows_inserted} event rows...")

    conn.commit()

    print("\nTable Statistics:")
    print("-" * 50)
    # Dynamically fetch user-defined tables sorted alphabetically
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]
    for tbl in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM [{tbl}]")
            cnt = cursor.fetchone()[0]
            print(f"  {tbl:<15} : {cnt:,} rows")
        except sqlite3.OperationalError:
            print(f"  {tbl:<15} : Table does not exist")
    print("-" * 50)

    # Emit final SQL schema to output/schema.sql
    schema_path = os.path.join("output", "schema.sql")
    try:
        cursor.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type DESC, name")
        schema_rows = cursor.fetchall()
        schema_statements = []
        for row in schema_rows:
            stmt = row[0].strip()
            if not stmt.endswith(";"):
                stmt += ";"
            schema_statements.append(stmt)
        schema_content = "\n\n".join(schema_statements)
        with open(schema_path, "w", encoding="utf-8") as f:
            f.write(schema_content + "\n")
        print(f"Emitted database schema to: {schema_path}")
    except Exception as e:
        print(f"Failed to emit database schema: {e}")

    conn.close()
    print(f"\nSuccessfully finished ingestion!")
    print(f"Total sessions: {len(registered_sessions)}")
    print(f"Total event rows loaded: {total_rows_inserted}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Ingest Claude session logs into SQLite.')
    parser.add_argument('--since', type=lambda s: datetime.strptime(s, '%Y-%m-%dT%H:%M:%S'),
                        metavar='YYYY-MM-DDTHH:MM:SS',
                        help='Only re-ingest sessions modified since this timestamp (incremental mode).')
    args = parser.parse_args()
    ingest_files(since=args.since)
