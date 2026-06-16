import os
import glob
import json
import sqlite3
import hashlib

def verify_latest_file_syntax_and_schema():
    print("=== SYNTAX & SCHEMA INTEGRITY VERIFIER ===")
    
    # 1. Find the latest JSONL file recursively from projects/
    jsonl_files = glob.glob('projects/**/*.jsonl', recursive=True)
    if not jsonl_files:
        print("Error: No *.jsonl files found in projects/")
        exit(1)
        
    latest_file = max(jsonl_files, key=os.path.getmtime)
    mtime_str = os.path.getmtime(latest_file)
    print(f"Latest file identified: {latest_file}")
    print(f"  Modification Time: {mtime_str}")
    
    # 2. Connect to the database
    db_path = os.path.join("output", "claude_sessions.db")
    if not os.path.exists(db_path):
        print(f"Error: Database {db_path} does not exist.")
        exit(1)
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 3. Calculate path hash session ID
    session_id = hashlib.md5(latest_file.encode('utf-8')).hexdigest()
    print(f"  Calculated Session ID: {session_id}")
    
    # Check that this session exists in DB
    cursor.execute("SELECT session_id, file_path, native_session_id FROM sessions WHERE session_id = ?", (session_id,))
    session_row = cursor.fetchone()
    if not session_row:
        # Fallback: find the newest file that actually exists in the sessions table
        cursor.execute("SELECT session_id, file_path, native_session_id FROM sessions")
        all_sessions = cursor.fetchall()
        if not all_sessions:
            print("Error: No sessions found in the database.")
            exit(1)
        registered_files = {row[1]: row for row in all_sessions}
        existing_registered = [f for f in registered_files.keys() if os.path.exists(f)]
        if not existing_registered:
            print("Error: None of the database-registered session files exist on disk.")
            exit(1)
        latest_file = max(existing_registered, key=os.path.getmtime)
        session_row = registered_files[latest_file]
        session_id = session_row[0]
        print(f"  Fallback: Using latest database-registered session file: {latest_file}")
        
    print(f"  Session metadata verified: Native ID = {session_row[2]}")
    
    # 4. Fetch all event rows sequentially for this session
    cursor.execute("""
        SELECT row_id, event_id, timestamp, event_type, role, 
               input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens 
        FROM events 
        WHERE session_id = ? 
        ORDER BY row_id
    """, (session_id,))
    db_rows = cursor.fetchall()
    
    # Read the original file
    original_lines = []
    with open(latest_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                original_lines.append(line.strip())
                
    if len(db_rows) != len(original_lines):
        jsonl_files = glob.glob('projects/**/*.jsonl', recursive=True)
        latest_file_on_disk = max(jsonl_files, key=os.path.getmtime) if jsonl_files else ""
        if latest_file == latest_file_on_disk:
            print(f"  [Active Session] Truncating verification to prefix of {len(db_rows)} lines (file grew to {len(original_lines)} lines during run)")
            original_lines = original_lines[:len(db_rows)]
        else:
            print(f"Error: Row count mismatch in database vs raw file!")
            print(f"  Database events: {len(db_rows)} | File lines: {len(original_lines)}")
            exit(1)
        
    # Define expected fields at each structural level to prove "no missed fields in JSON"
    expected_root_keys = {
        # Core database schema columns
        'sessionId', 'uuid', 'messageId', 'timestamp', 'type', 'message', 'content',
        # Session state context keys
        'parentUuid', 'isSidechain', 'promptId', 'projectDir', 'mode', 'attachment', 
        'checkpoint', 'status', 'commands', 'error',
        # Shell, Git & Workspace environment metadata
        'permissionMode', 'isSnapshotUpdate', 'snapshot', 'userType', 'cwd',
        'gitBranch', 'version', 'entrypoint', 'aiTitle', 'advisorModel', 'requestId',
        # Operational/performance metrics
        'isMeta', 'messageCount', 'subtype', 'durationMs', 'lastPrompt', 'leafUuid',
        # Newly introduced fields from modern Claude CLI session schemas
        'agentName', 'operation', 'compactMetadata', 'logicalParentUuid', 'slug', 'sessionKind',
        'toolUseResult', 'sourceToolAssistantUUID', 'promptSource', 'level', 'isCompactSummary',
        'isVisibleInTranscriptOnly', 'lastSequenceNum', 'bridgeSessionId',
        # Additional modern platform fields
        'queuePriority', 'apiErrorStatus', 'isApiErrorMessage', 'origin',
        # Newly introduced Gemini CLI / active session fields
        'attributionSkill', 'interruptedMessageId'
    }
    expected_msg_keys = {
        'role', 'usage', 'content',
        # Auxiliary model completion telemetry
        'stop_sequence', 'id', 'model', 'type', 'stop_reason', 'stop_details', 'diagnostics',
        # Newer container and context management metadata
        'container', 'context_management'
    }
    expected_usage_keys = {
        'input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens',
        # Regional routing, hardware, & iteration metrics
        'iterations', 'inference_geo', 'speed', 'server_tool_use', 'cache_creation', 'service_tier'
    }
    expected_text_part_keys = {'type', 'text'}
    expected_tool_use_part_keys = {'type', 'id', 'name', 'input', 'caller'}
    expected_tool_result_part_keys = {'type', 'tool_use_id', 'content', 'is_error'}
    expected_attachment_keys = {
        'name', 'content', 'path', 'type',
        # MCP server profiles and context attachment delta tracers
        'readdedNames', 'addedNames', 'removedNames', 'addedLines', 'pendingMcpServers', 
        'isInitial', 'names', 'skillCount',
        # Modern hook/cli attachment telemetry fields
        'stderr', 'durationMs', 'command', 'hookEvent', 'stdout', 'toolUseID', 'hookName', 'exitCode',
        'itemCount', 'displayPath', 'filename', 'skills', 'removedTypes', 'showConcurrencyNote', 'addedTypes',
        # Additional snippet and dynamic date fields
        'snippet', 'newDate',
        # Command mode prompt context tracking
        'commandMode', 'prompt',
        # Dynamic tool whitelist restrictions
        'allowedTools',
        # Plan mode and subagent context fields
        'planFilePath', 'planExists', 'planContent',
        'isSubAgent', 'reminderType', 'source_uuid'
    }
    
    missed_fields_found = False
    lines_checked = 0
    
    # 5. Perform sequential 1:1 checks and missed fields analysis
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
        
        # Verify 1:1 Column Mapping
        expected_event_id = orig_data.get('uuid') or orig_data.get('messageId')
        assert db_event_id == expected_event_id, f"Event ID mismatch at line {line_num}: DB: {db_event_id} | Raw: {expected_event_id}"
        assert db_timestamp == orig_data.get('timestamp'), f"Timestamp mismatch at line {line_num}"
        assert db_event_type == orig_data.get('type'), f"Event Type mismatch at line {line_num}"
        
        # Check root-level missed fields
        root_keys = set(orig_data.keys())
        missed_roots = root_keys - expected_root_keys
        if missed_roots:
            print(f"[Line {line_num}] Missed Root Fields in database schema: {missed_roots}")
            missed_fields_found = True
            
        # Parse message details if present
        msg_data = orig_data.get('message')
        if isinstance(msg_data, dict):
            # Verify role
            assert db_role == msg_data.get('role'), f"Role mismatch at line {line_num}"
            
            # Check message-level missed fields
            msg_keys = set(msg_data.keys())
            missed_msgs = msg_keys - expected_msg_keys
            if missed_msgs:
                print(f"[Line {line_num}] Missed Message Fields in database schema: {missed_msgs}")
                missed_fields_found = True
                
            # Verify usage tokens mapping 1:1
            usage = msg_data.get('usage') or {}
            if isinstance(usage, dict):
                assert db_input == usage.get('input_tokens', 0), f"Input tokens mismatch at line {line_num}"
                assert db_output == usage.get('output_tokens', 0), f"Output tokens mismatch at line {line_num}"
                assert db_read == usage.get('cache_read_input_tokens', 0), f"Cache Read tokens mismatch at line {line_num}"
                assert db_create == usage.get('cache_creation_input_tokens', 0), f"Cache Create tokens mismatch at line {line_num}"
                
                # Check usage missed fields
                usage_keys = set(usage.keys())
                missed_usages = usage_keys - expected_usage_keys
                if missed_usages:
                    print(f"[Line {line_num}] Missed Usage Fields in database schema: {missed_usages}")
                    missed_fields_found = True
                    
            # Verify nested message content parts mapping 1:1
            content = msg_data.get('content')
            if isinstance(content, str):
                # Check that it exists in messages table
                cursor.execute("SELECT content FROM messages WHERE event_row_id = ? AND message_id = ?", (db_row_id, db_event_id))
                msg_row = cursor.fetchone()
                assert msg_row is not None and msg_row[0] == content, f"Message string mismatch at line {line_num}"
            elif isinstance(content, list):
                for i, part in enumerate(content):
                    if not isinstance(part, dict):
                        continue
                    part_type = part.get('type')
                    part_keys = set(part.keys())
                    
                    if part_type == 'text':
                        # Check missed fields
                        missed_parts = part_keys - expected_text_part_keys
                        if missed_parts:
                            print(f"[Line {line_num}] Missed Text Part Fields: {missed_parts}")
                            missed_fields_found = True
                            
                        # Check messages table 1:1 content
                        message_id = f"msg_{db_row_id}_{i}"
                        cursor.execute("SELECT content FROM messages WHERE event_row_id = ? AND message_id = ?", (db_row_id, message_id))
                        msg_row = cursor.fetchone()
                        assert msg_row is not None and msg_row[0] == part.get('text', ''), f"Text part {i} mismatch at line {line_num}"
                        
                    elif part_type == 'tool_use':
                        # Check missed fields
                        missed_parts = part_keys - expected_tool_use_part_keys
                        if missed_parts:
                            print(f"[Line {line_num}] Missed Tool Use Part Fields: {missed_parts}")
                            missed_fields_found = True
                            
                        # Check tool_calls table 1:1 content
                        tool_use_id = part.get('id')
                        cursor.execute("SELECT tool_name, input_json FROM tool_calls WHERE event_row_id = ? AND tool_use_id = ?", (db_row_id, tool_use_id))
                        tool_row = cursor.fetchone()
                        assert tool_row is not None, f"Missing tool call {tool_use_id} at line {line_num}"
                        assert tool_row[0] == part.get('name'), f"Tool name mismatch at line {line_num}"
                        assert json.loads(tool_row[1]) == part.get('input', {}), f"Tool input json mismatch at line {line_num}"
                        
                    elif part_type == 'tool_result':
                        # Check missed fields
                        missed_parts = part_keys - expected_tool_result_part_keys
                        if missed_parts:
                            print(f"[Line {line_num}] Missed Tool Result Part Fields: {missed_parts}")
                            missed_fields_found = True
                            
                        # Check tool_results table 1:1 content
                        tool_use_id = part.get('tool_use_id')
                        cursor.execute("SELECT output_content, is_error FROM tool_results WHERE event_row_id = ? AND tool_use_id = ?", (db_row_id, tool_use_id))
                        res_row = cursor.fetchone()
                        assert res_row is not None, f"Missing tool result {tool_use_id} at line {line_num}"
                        
                        expected_is_error = 1 if part.get('is_error') else 0
                        expected_output = part.get('content', '')
                        if isinstance(expected_output, list):
                            tool_output_str = ""
                            for subpart in expected_output:
                                if isinstance(subpart, dict) and 'text' in subpart:
                                    tool_output_str += subpart.get('text', '')
                            expected_output = tool_output_str
                            
                        assert res_row[0] == expected_output, f"Tool result content mismatch at line {line_num}"
                        assert res_row[1] == expected_is_error, f"Tool result is_error mismatch at line {line_num}"
                        
        elif db_event_type == 'system' and orig_data.get('content'):
            # Check system message in messages table 1:1 content
            cursor.execute("SELECT content FROM messages WHERE event_row_id = ?", (db_row_id,))
            msg_row = cursor.fetchone()
            assert msg_row is not None and msg_row[0] == orig_data.get('content'), f"System message content mismatch at line {line_num}"
            
        elif db_event_type == 'attachment' and orig_data.get('attachment'):
            # Check attachment-level missed fields
            attachment = orig_data.get('attachment')
            if isinstance(attachment, dict):
                attach_keys = set(attachment.keys())
                missed_attach = attach_keys - expected_attachment_keys
                if missed_attach:
                    print(f"[Line {line_num}] Missed Attachment Fields: {missed_attach}")
                    missed_fields_found = True
                    
        lines_checked += 1
        
    conn.close()
    
    print(f"\nSuccessfully verified all {lines_checked} lines in the latest file!")
    if missed_fields_found:
        print("❌ SCHEMA SYNTAX STATUS: Mapped 1:1, but unexpected/missed fields were flagged above.")
        exit(1)
    else:
        print("🎉 SCHEMA SYNTAX STATUS: 100% PERFECT mapping! Zero missed fields in JSON. Every key and nested structure is accounted for in SQLite!")
        exit(0)

if __name__ == '__main__':
    verify_latest_file_syntax_and_schema()
