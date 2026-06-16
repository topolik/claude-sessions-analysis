import os
import sqlite3
import glob
import json

def setup_database(conn):
    cursor = conn.cursor()

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
        output_content TEXT,
        is_error INTEGER,
        PRIMARY KEY (event_row_id, tool_use_id),
        FOREIGN KEY(event_row_id) REFERENCES events(row_id)
    );
    """)

    # 6. Strict Event Metadata Table (Auxiliary event fields at root, message, and usage levels)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS event_metadata (
        event_row_id INTEGER,
        parent_key TEXT,
        key TEXT,
        value_json TEXT,
        PRIMARY KEY (event_row_id, parent_key, key),
        FOREIGN KEY(event_row_id) REFERENCES events(row_id)
    );
    """)

    # 7. Strict Content Part Metadata Table (Auxiliary message part keys)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS part_metadata (
        event_row_id INTEGER,
        part_index INTEGER,
        key TEXT,
        value_json TEXT,
        PRIMARY KEY (event_row_id, part_index, key),
        FOREIGN KEY(event_row_id) REFERENCES events(row_id)
    );
    """)

    # Performance Indices
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_event ON messages(event_row_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tool_calls_event ON tool_calls(event_row_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tool_results_event ON tool_results(event_row_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_event_metadata_row ON event_metadata(event_row_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_part_metadata_row ON part_metadata(event_row_id);")
    conn.commit()

def ingest_files():
    db_path = os.path.join("output", "claude_sessions.db")
    os.makedirs("output", exist_ok=True)
    
    # If old DB exists, delete it for a clean re-load
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"Removed existing database: {db_path}")

    conn = sqlite3.connect(db_path)
    setup_database(conn)
    cursor = conn.cursor()

    # Find all JSONL files recursively
    file_pattern = os.path.join("projects", "**", "*.jsonl")
    jsonl_files = glob.glob(file_pattern, recursive=True)
    print(f"Found {len(jsonl_files)} session log files to ingest.")

    registered_sessions = set()
    total_rows_inserted = 0

    for file_idx, file_path in enumerate(jsonl_files, 1):
        # 1. Generate unique file-level session_id
        import hashlib
        session_id = hashlib.md5(file_path.encode('utf-8')).hexdigest()

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

                    # Insert core event
                    cursor.execute("""
                    INSERT INTO events (session_id, event_id, timestamp, event_type, role, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (session_id, event_id, timestamp, event_type, role, input_tokens, output_tokens, cache_read, cache_create))

                    event_row_id = cursor.lastrowid
                    total_rows_inserted += 1

                    # Store all auxiliary root-level metadata
                    for k, v in data.items():
                        if k not in ('uuid', 'messageId', 'timestamp', 'type', 'sessionId', 'message'):
                            if k == 'content' and event_type == 'system':
                                continue
                            cursor.execute("""
                            INSERT OR REPLACE INTO event_metadata (event_row_id, parent_key, key, value_json)
                            VALUES (?, ?, ?, ?)
                            """, (event_row_id, 'root', k, json.dumps(v)))

                    # Parse message/tool contents for query structured tables
                    if isinstance(msg_data, dict):
                        # Store all auxiliary message-level metadata
                        for k, v in msg_data.items():
                            if k not in ('role', 'usage', 'content'):
                                cursor.execute("""
                                INSERT OR REPLACE INTO event_metadata (event_row_id, parent_key, key, value_json)
                                VALUES (?, ?, ?, ?)
                                """, (event_row_id, 'message', k, json.dumps(v)))

                        # Store all auxiliary usage-level metadata
                        usage = msg_data.get('usage') or {}
                        if isinstance(usage, dict):
                            for k, v in usage.items():
                                if k not in ('input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens'):
                                    cursor.execute("""
                                    INSERT OR REPLACE INTO event_metadata (event_row_id, parent_key, key, value_json)
                                    VALUES (?, ?, ?, ?)
                                    """, (event_row_id, 'usage', k, json.dumps(v)))

                        content = msg_data.get('content')
                        if isinstance(content, str):
                            message_id = event_id or f"msg_{event_row_id}"
                            cursor.execute("INSERT OR REPLACE INTO messages (message_id, event_row_id, content) VALUES (?, ?, ?)", (message_id, event_row_id, content))
                        elif isinstance(content, list):
                            for i, part in enumerate(content):
                                if not isinstance(part, dict):
                                    continue
                                part_type = part.get('type')
                                if part_type == 'text':
                                    text = part.get('text', '')
                                    message_id = f"msg_{event_row_id}_{i}"
                                    cursor.execute("INSERT OR REPLACE INTO messages (message_id, event_row_id, content) VALUES (?, ?, ?)", (message_id, event_row_id, text))
                                    # Store auxiliary text-part keys if any
                                    for pk, pv in part.items():
                                        if pk not in ('type', 'text'):
                                            cursor.execute("INSERT OR REPLACE INTO part_metadata (event_row_id, part_index, key, value_json) VALUES (?, ?, ?, ?)", (event_row_id, i, pk, json.dumps(pv)))
                                elif part_type == 'tool_use':
                                    tool_use_id = part.get('id')
                                    tool_name = part.get('name')
                                    tool_input = json.dumps(part.get('input', {}))
                                    cursor.execute("INSERT OR REPLACE INTO tool_calls (tool_use_id, event_row_id, tool_name, input_json) VALUES (?, ?, ?, ?)", (tool_use_id, event_row_id, tool_name, tool_input))
                                    # Store auxiliary tool_use-part keys if any
                                    for pk, pv in part.items():
                                        if pk not in ('type', 'id', 'name', 'input'):
                                            cursor.execute("INSERT OR REPLACE INTO part_metadata (event_row_id, part_index, key, value_json) VALUES (?, ?, ?, ?)", (event_row_id, i, pk, json.dumps(pv)))
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
                                    cursor.execute("INSERT OR REPLACE INTO tool_results (tool_use_id, event_row_id, output_content, is_error) VALUES (?, ?, ?, ?)", (tool_use_id, event_row_id, tool_output, is_error))
                                    # Store auxiliary tool_result-part keys if any (e.g. content structure if complex, or other fields)
                                    for pk, pv in part.items():
                                        if pk not in ('type', 'tool_use_id', 'is_error'):
                                            cursor.execute("INSERT OR REPLACE INTO part_metadata (event_row_id, part_index, key, value_json) VALUES (?, ?, ?, ?)", (event_row_id, i, pk, json.dumps(pv)))
                                else:
                                    # For other part types (e.g. thinking, signature), store all keys in part_metadata
                                    for pk, pv in part.items():
                                        cursor.execute("INSERT OR REPLACE INTO part_metadata (event_row_id, part_index, key, value_json) VALUES (?, ?, ?, ?)", (event_row_id, i, pk, json.dumps(pv)))

                    elif event_type == 'system' and data.get('content'):
                        message_id = f"sys_{event_row_id}"
                        cursor.execute("INSERT OR REPLACE INTO messages (message_id, event_row_id, content) VALUES (?, ?, ?)", (message_id, event_row_id, data.get('content')))

                    # For system and attachment events, also store attachments in part_metadata or event_metadata
                    if event_type == 'attachment' and data.get('attachment'):
                        attachment = data.get('attachment')
                        if isinstance(attachment, dict):
                            for k, v in attachment.items():
                                cursor.execute("""
                                INSERT OR REPLACE INTO part_metadata (event_row_id, part_index, key, value_json)
                                VALUES (?, ?, ?, ?)
                                """, (event_row_id, -1, k, json.dumps(v)))

        except Exception as e:
            print(f"Error reading file {file_path}: {e}")

        # Commit periodically (every 10 files) to boost efficiency and safety
        if file_idx % 10 == 0:
            conn.commit()
            print(f"Ingested {file_idx}/{len(jsonl_files)} files. Inserted {total_rows_inserted} event rows...")

    conn.commit()
    conn.close()
    print(f"\nSuccessfully finished ingestion!")
    print(f"Total sessions: {len(registered_sessions)}")
    print(f"Total event rows loaded: {total_rows_inserted}")

if __name__ == '__main__':
    ingest_files()
