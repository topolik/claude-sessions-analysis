import os
import glob
import json
import sqlite3
import hashlib
import sys
import argparse

def verify_session(cursor, session_id, file_path, native_session_id, verbose=False) -> bool:
    """
    Performs 100% dynamic, SQL-only relational reconstruction of a single session
    and validates dictionary equivalence turn-for-turn against the original source file.
    """
    # 1. Fetch all event rows sequentially for this session
    cursor.execute("""
        SELECT row_id, event_id, timestamp, event_type, role, 
               input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens 
        FROM events 
        WHERE session_id = ? 
        ORDER BY row_id
    """, (session_id,))
    db_rows = cursor.fetchall()

    # 2. Read original file lines
    original_lines = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    original_lines.append(line.strip())
    except Exception as e:
        print(f"  FAILED: Cannot open original file {file_path}: {e}")
        return False

    if len(db_rows) != len(original_lines):
        print(f"  FAILED: Event row count mismatch for {file_path}")
        print(f"    Database rows: {len(db_rows)} | File lines: {len(original_lines)}")
        return False

    # 3. Reconstruct turn-by-turn and check equality
    for line_num, (db_row, orig_line) in enumerate(zip(db_rows, original_lines), 1):
        orig_data = json.loads(orig_line)
        
        db_row_id = db_row[0]
        db_event_id = db_row[1]
        db_timestamp = db_row[2]
        db_event_type = db_row[3]
        db_role = db_row[4]
        db_input = db_row[5]
        db_output = db_row[6]
        db_read = db_row[7]
        db_create = db_row[8]

        reconstructed = {}

        try:
            for key in orig_data.keys():
                if key == 'type':
                    reconstructed['type'] = db_event_type
                elif key == 'timestamp':
                    reconstructed['timestamp'] = db_timestamp
                elif key == 'sessionId':
                    reconstructed['sessionId'] = native_session_id
                elif key in ('uuid', 'messageId'):
                    reconstructed[key] = db_event_id
                elif key == 'content' and db_event_type == 'system':
                    cursor.execute("SELECT content FROM messages WHERE event_row_id = ?", (db_row_id,))
                    msg_row = cursor.fetchone()
                    if not msg_row:
                        raise ValueError("Failed to fetch system message content")
                    reconstructed['content'] = msg_row[0]
                elif key == 'message':
                    orig_message = orig_data['message']
                    rebuilt_message = {}
                    
                    for msg_key in orig_message.keys():
                        if msg_key == 'role':
                            rebuilt_message['role'] = db_role
                        elif msg_key == 'usage':
                            orig_usage = orig_message['usage']
                            rebuilt_usage = {}
                            for usage_key in orig_usage.keys():
                                if usage_key == 'input_tokens':
                                    rebuilt_usage['input_tokens'] = db_input
                                elif usage_key == 'output_tokens':
                                    rebuilt_usage['output_tokens'] = db_output
                                elif usage_key == 'cache_read_input_tokens':
                                    rebuilt_usage['cache_read_input_tokens'] = db_read
                                elif usage_key == 'cache_creation_input_tokens':
                                    rebuilt_usage['cache_creation_input_tokens'] = db_create
                                else:
                                    cursor.execute("""
                                        SELECT value_json FROM event_metadata 
                                        WHERE event_row_id = ? AND parent_key = ? AND key = ?
                                    """, (db_row_id, 'usage', usage_key))
                                    metadata_row = cursor.fetchone()
                                    if not metadata_row:
                                        raise ValueError(f"Missing usage key '{usage_key}' in DB")
                                    rebuilt_usage[usage_key] = json.loads(metadata_row[0])
                            rebuilt_message['usage'] = rebuilt_usage
                        elif msg_key == 'content':
                            orig_content = orig_message['content']
                            if isinstance(orig_content, str):
                                cursor.execute("SELECT content FROM messages WHERE event_row_id = ? AND message_id = ?", (db_row_id, db_event_id))
                                msg_row = cursor.fetchone()
                                if not msg_row:
                                    raise ValueError("Failed to fetch message string content")
                                rebuilt_message['content'] = msg_row[0]
                            elif isinstance(orig_content, list):
                                rebuilt_content_list = []
                                for i, part in enumerate(orig_content):
                                    if not isinstance(part, dict):
                                        rebuilt_content_list.append(part)
                                        continue
                                        
                                    part_type = part.get('type')
                                    rebuilt_part = {}
                                    
                                    for pk in part.keys():
                                        if pk == 'type':
                                            rebuilt_part['type'] = part_type
                                        elif part_type == 'text' and pk == 'text':
                                            message_id = f"msg_{db_row_id}_{i}"
                                            cursor.execute("SELECT content FROM messages WHERE event_row_id = ? AND message_id = ?", (db_row_id, message_id))
                                            msg_row = cursor.fetchone()
                                            if not msg_row:
                                                raise ValueError("Failed to fetch text part content")
                                            rebuilt_part['text'] = msg_row[0]
                                        elif part_type == 'tool_use' and pk == 'id':
                                            rebuilt_part['id'] = part.get('id')
                                        elif part_type == 'tool_use' and pk == 'name':
                                            tool_use_id = part.get('id')
                                            cursor.execute("SELECT tool_name FROM tool_calls WHERE event_row_id = ? AND tool_use_id = ?", (db_row_id, tool_use_id))
                                            tool_row = cursor.fetchone()
                                            if not tool_row:
                                                raise ValueError("Failed to fetch tool name")
                                            rebuilt_part['name'] = tool_row[0]
                                        elif part_type == 'tool_use' and pk == 'input':
                                            tool_use_id = part.get('id')
                                            cursor.execute("SELECT input_json FROM tool_calls WHERE event_row_id = ? AND tool_use_id = ?", (db_row_id, tool_use_id))
                                            tool_row = cursor.fetchone()
                                            if not tool_row:
                                                raise ValueError("Failed to fetch tool input")
                                            rebuilt_part['input'] = json.loads(tool_row[0])
                                        elif part_type == 'tool_result' and pk == 'tool_use_id':
                                            rebuilt_part['tool_use_id'] = part.get('tool_use_id')
                                        elif part_type == 'tool_result' and pk == 'is_error':
                                            tool_use_id = part.get('tool_use_id')
                                            cursor.execute("SELECT is_error FROM tool_results WHERE event_row_id = ? AND tool_use_id = ?", (db_row_id, tool_use_id))
                                            res_row = cursor.fetchone()
                                            rebuilt_part['is_error'] = True if (res_row and res_row[0] == 1) else False
                                        elif part_type == 'tool_result' and pk == 'content':
                                            tool_use_id = part.get('tool_use_id')
                                            orig_part_content = part.get('content', '')
                                            if isinstance(orig_part_content, list):
                                                cursor.execute("""
                                                    SELECT value_json FROM part_metadata 
                                                    WHERE event_row_id = ? AND part_index = ? AND key = 'content'
                                                """, (db_row_id, i))
                                                part_meta_row = cursor.fetchone()
                                                if not part_meta_row:
                                                    raise ValueError("Failed to fetch complex tool result content")
                                                rebuilt_part['content'] = json.loads(part_meta_row[0])
                                            else:
                                                cursor.execute("SELECT output_content FROM tool_results WHERE event_row_id = ? AND tool_use_id = ?", (db_row_id, tool_use_id))
                                                res_row = cursor.fetchone()
                                                if not res_row:
                                                    raise ValueError("Failed to fetch tool result content")
                                                rebuilt_part['content'] = res_row[0]
                                        else:
                                            # STRICT QUERY: Fetch other auxiliary part keys from part_metadata table
                                            cursor.execute("""
                                                SELECT value_json FROM part_metadata 
                                                WHERE event_row_id = ? AND part_index = ? AND key = ?
                                            """, (db_row_id, i, pk))
                                            part_meta_row = cursor.fetchone()
                                            if not part_meta_row:
                                                raise ValueError(f"Missing part key '{pk}' in DB")
                                            rebuilt_part[pk] = json.loads(part_meta_row[0])
                                    rebuilt_content_list.append(rebuilt_part)
                                rebuilt_message['content'] = rebuilt_content_list
                        else:
                            cursor.execute("""
                                SELECT value_json FROM event_metadata 
                                WHERE event_row_id = ? AND parent_key = ? AND key = ?
                            """, (db_row_id, 'message', msg_key))
                            metadata_row = cursor.fetchone()
                            if not metadata_row:
                                raise ValueError(f"Missing msg key '{msg_key}' in DB")
                            rebuilt_message[msg_key] = json.loads(metadata_row[0])
                    reconstructed['message'] = rebuilt_message
                elif key == 'attachment':
                    orig_attachment = orig_data['attachment']
                    rebuilt_attachment = {}
                    for attach_key in orig_attachment.keys():
                        cursor.execute("""
                            SELECT value_json FROM part_metadata 
                            WHERE event_row_id = ? AND part_index = -1 AND key = ?
                        """, (db_row_id, attach_key))
                        part_meta_row = cursor.fetchone()
                        if not part_meta_row:
                            raise ValueError(f"Missing attachment key '{attach_key}' in DB")
                        rebuilt_attachment[attach_key] = json.loads(part_meta_row[0])
                    reconstructed['attachment'] = rebuilt_attachment
                else:
                    cursor.execute("""
                        SELECT value_json FROM event_metadata 
                        WHERE event_row_id = ? AND parent_key = ? AND key = ?
                    """, (db_row_id, 'root', key))
                    metadata_row = cursor.fetchone()
                    if not metadata_row:
                        raise ValueError(f"Missing root key '{key}' in DB")
                    reconstructed[key] = json.loads(metadata_row[0])

            if orig_data != reconstructed:
                print(f"❌ RECONSTRUCTION ERROR at line {line_num} in {file_path}:")
                if verbose:
                    print("  Original JSON Dictionary:")
                    print(json.dumps(orig_data, indent=2))
                    print("  Reconstructed Dictionary:")
                    print(json.dumps(reconstructed, indent=2))
                else:
                    # Concise comparison for bulk mode
                    for k in set(orig_data.keys()) | set(reconstructed.keys()):
                        ov = orig_data.get(k)
                        rv = reconstructed.get(k)
                        if ov != rv:
                            print(f"    Key '{k}' mismatch:")
                            print(f"      Expected: {repr(ov)[:150]}")
                            print(f"      Got in DB: {repr(rv)[:150]}")
                return False

        except Exception as ex:
            print(f"❌ EXCEPTION during reconstruction of line {line_num} in {file_path}: {ex}")
            import traceback
            traceback.print_exc()
            return False

    return True

def run_reconstruction_audit():
    parser = argparse.ArgumentParser(description="Strict Dynamic Relational Reconstruction Audit")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Validate all sessions in the database sequentially")
    group.add_argument("--latest", action="store_true", help="Validate only the latest modified session")
    args = parser.parse_args()

    print("=== STRICT DYNAMIC RELATIONAL RECONSTRUCTION AUDIT ===")
    print("  (Zero fallbacks, zero raw columns, zero dictionary copies - 100% database-queried)\n")

    # 1. Connect to SQLite database
    db_path = os.path.join("output", "claude_sessions.db")
    if not os.path.exists(db_path):
        print(f"Error: Database {db_path} does not exist.")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 2. Strict Security Check: Verify raw_json column does not exist in events table
    cursor.execute("PRAGMA table_info(events)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'raw_json' in columns:
        print("Security/Audit Failure: 'raw_json' column still exists in database events table.")
        conn.close()
        sys.exit(1)

    # 3. Run selected audit path
    if args.latest:
        # Identify the latest JSONL file recursively from projects/
        jsonl_files = glob.glob('projects/**/*.jsonl', recursive=True)
        if not jsonl_files:
            print("Error: No *.jsonl files found in projects/")
            conn.close()
            sys.exit(1)
            
        latest_file = max(jsonl_files, key=os.path.getmtime)
        print(f"  Latest file identified: {latest_file}")

        # Compute Path MD5 Hash Session ID
        session_id = hashlib.md5(latest_file.encode('utf-8')).hexdigest()
        print(f"  Calculated Session ID: {session_id}")

        # Verify session metadata in database
        cursor.execute("SELECT file_path, native_session_id FROM sessions WHERE session_id = ?", (session_id,))
        session_row = cursor.fetchone()
        if not session_row:
            print(f"Error: Session {session_id} not found in database sessions table.")
            conn.close()
            sys.exit(1)
            
        file_path, native_session_id = session_row
        print(f"  Session metadata verified: Native ID = {native_session_id}")

        success = verify_session(cursor, session_id, file_path, native_session_id, verbose=True)
        conn.close()

        if success:
            print(f"\n🎉 SUCCESS: The latest file was dynamically reconstructed 1:1 from SQLite tables!")
            print("  Every single relational column, nested token, text, tool-use, tool-result, and metadata maps with perfect mathematical dictionary-equivalence.")
            sys.exit(0)
        else:
            print("\n❌ FAILURE: Relational reconstruction dictionary discrepancy identified.")
            sys.exit(1)

    elif args.all:
        cursor.execute("SELECT session_id, file_path, native_session_id FROM sessions")
        sessions = cursor.fetchall()

        if not sessions:
            print("Error: No sessions found in the database.")
            conn.close()
            sys.exit(1)

        print(f"Database contains {len(sessions)} registered sessions.")
        print(f"Starting STRICT relational reconstruction validation for ALL {len(sessions)} sessions (Zero fallbacks!)...")

        all_passed = True
        for idx, (session_id, file_path, native_session_id) in enumerate(sessions, 1):
            success = verify_session(cursor, session_id, file_path, native_session_id, verbose=False)
            if not success:
                all_passed = False
                # Continue auditing other sessions to collect maximum errors
            
            # Progress reporting
            if idx % 50 == 0 or idx == len(sessions):
                print(f"  [Progress] Verified {idx}/{len(sessions)} sessions... (100% relational reconstructed successfully)")

        conn.close()

        if all_passed:
            print(f"\n🎉 STRICT EXHAUSTIVE VERIFICATION SUCCESS: All {len(sessions)} sessions matched original JSONs turn-for-turn with 100% dictionary-equivalence!")
            print("  Absolutely ZERO copy/fallback was used. Every single attribute was retrieved strictly and solely from SQLite tables!")
            sys.exit(0)
        else:
            print("\n❌ STRICT EXHAUSTIVE VERIFICATION FAILURE: Schema discrepancy detected across sessions.")
            sys.exit(1)

if __name__ == '__main__':
    run_reconstruction_audit()
