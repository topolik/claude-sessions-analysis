import os
import sqlite3
import pandas as pd

def profile_database():
    db_path = os.path.join("output", "claude_sessions.db")
    if not os.path.exists(db_path):
        print(f"Error: Database {db_path} does not exist.")
        exit(1)

    conn = sqlite3.connect(db_path)
    
    # We will compile the report content into a Markdown string
    report = []
    report.append("# Relational Database Schema Profiling & Field-Level Usage Report\n")
    report.append("This report profiles every table and column in `output/claude_sessions.db` to show field population rates, value distributions, and categorical breakdowns. This forms a structural map to enable future complex cross-field analytical queries.\n")

    # 1. High Level Row Counts
    report.append("## 1. Table-Level High-Level Metrics")
    report.append("| Table Name | Total Rows | description |")
    report.append("| :--- | :--- | :--- |")
    for table in ["sessions", "events", "messages", "tool_calls", "tool_results", "event_metadata", "part_metadata"]:
        count = pd.read_sql_query(f"SELECT COUNT(*) as cnt FROM {table}", conn).iloc[0]["cnt"]
        desc = {
            "sessions": "Unique user session references.",
            "events": "Chronological stream of all transaction events (user, assistant, system, etc.).",
            "messages": "Full parsed textual content of messages.",
            "tool_calls": "Detailed invocations of tool use by the assistant.",
            "tool_results": "Execution output content and status for tool calls.",
            "event_metadata": "Entity-Attribute-Value relational storage for auxiliary event metadata.",
            "part_metadata": "Entity-Attribute-Value relational storage for auxiliary message parts delta variables."
        }[table]
        report.append(f"| `{table}` | {count:,} | {desc} |")
    report.append("\n")

    # 2. Detailed Field Profiling (Column by Column Population & Distinctness)
    report.append("## 2. Column-by-Column Population & Distinctness Profiles")
    tables_cols = {
        "sessions": ["session_id", "file_path", "native_session_id"],
        "events": ["row_id", "session_id", "event_id", "timestamp", "event_type", "role", "input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens"],
        "messages": ["message_id", "event_row_id", "content"],
        "tool_calls": ["tool_use_id", "event_row_id", "tool_name", "input_json"],
        "tool_results": ["tool_use_id", "event_row_id", "output_content", "is_error"],
        "event_metadata": ["event_row_id", "parent_key", "key", "value_json"],
        "part_metadata": ["event_row_id", "part_index", "key", "value_json"]
    }

    for table, columns in tables_cols.items():
        report.append(f"### Table: `{table}`")
        report.append("| Column Name | Populated Rows | Null/Default Rows | Population % | Unique Values |")
        report.append("| :--- | :--- | :--- | :--- | :--- |")
        
        # Get total rows
        total_rows = pd.read_sql_query(f"SELECT COUNT(*) as cnt FROM {table}", conn).iloc[0]["cnt"]
        if total_rows == 0:
            total_rows = 1 # Avoid division by zero
            
        for col in columns:
            # For token metrics, they are considered default if 0. For text/id columns, check NULL or empty.
            is_numeric_token = "tokens" in col or "cache" in col
            if is_numeric_token:
                null_query = f"SELECT COUNT(*) as cnt FROM {table} WHERE {col} = 0 OR {col} IS NULL"
            else:
                null_query = f"SELECT COUNT(*) as cnt FROM {table} WHERE {col} IS NULL OR {col} = ''"
                
            null_count = pd.read_sql_query(null_query, conn).iloc[0]["cnt"]
            populated_count = total_rows - null_count
            pop_pct = (populated_count / total_rows) * 100
            
            # Distinct values
            distinct_count = pd.read_sql_query(f"SELECT COUNT(DISTINCT {col}) as cnt FROM {table}", conn).iloc[0]["cnt"]
            
            report.append(f"| `{col}` | {populated_count:,} | {null_count:,} | {pop_pct:.2f}% | {distinct_count:,} |")
        report.append("\n")

    # 3. Categorical Distributions (breakdowns of key usage fields)
    report.append("## 3. Categorical Field Value Distributions")
    
    # Event Types
    report.append("### Event Type (`events.event_type`) Distribution")
    df_et = pd.read_sql_query("""
        SELECT event_type, COUNT(*) as count, 
               (COUNT(*) * 100.0 / (SELECT COUNT(*) FROM events)) as percentage
        FROM events GROUP BY event_type ORDER BY count DESC
    """, conn)
    report.append("| Event Type (`type`) | Count | Percentage |")
    report.append("| :--- | :--- | :--- |")
    for _, r in df_et.iterrows():
        report.append(f"| `{r['event_type']}` | {r['count']:,} | {r['percentage']:.2f}% |")
    report.append("\n")

    # Message Roles combined with Event Types
    report.append("### Message Roles & Co-occurrences (`events.event_type` + `events.role`)")
    df_role = pd.read_sql_query("""
        SELECT event_type, COALESCE(role, 'None') as role, COUNT(*) as count,
               (COUNT(*) * 100.0 / (SELECT COUNT(*) FROM events)) as percentage
        FROM events GROUP BY event_type, role ORDER BY count DESC
    """, conn)
    report.append("| Event Type | Role | Count | Percentage |")
    report.append("| :--- | :--- | :--- | :--- |")
    for _, r in df_role.iterrows():
        report.append(f"| `{r['event_type']}` | `{r['role']}` | {r['count']:,} | {r['percentage']:.2f}% |")
    report.append("\n")

    # Tool Name usage in Tool Calls
    report.append("### Tool Call (`tool_calls.tool_name`) Distribution")
    df_tools = pd.read_sql_query("""
        SELECT tool_name, COUNT(*) as count,
               (COUNT(*) * 100.0 / (SELECT COUNT(*) FROM tool_calls)) as percentage
        FROM tool_calls GROUP BY tool_name ORDER BY count DESC
    """, conn)
    report.append("| Tool Name | Invocation Count | Usage Percentage |")
    report.append("| :--- | :--- | :--- |")
    for _, r in df_tools.iterrows():
        report.append(f"| `{r['tool_name']}` | {r['count']:,} | {r['percentage']:.2f}% |")
    report.append("\n")

    # 4. Cross-Field Advanced Combinations
    report.append("## 4. Cross-Field Analytical Combinations")
    
    # Tool Name + Error Rate
    report.append("### Tool Call Failure and Success Rates (`tool_calls.tool_name` + `tool_results.is_error`)")
    df_failures = pd.read_sql_query("""
        SELECT tc.tool_name, 
               COUNT(tr.tool_use_id) as total_resolved,
               SUM(CASE WHEN tr.is_error = 1 THEN 1 ELSE 0 END) as failed_count,
               (SUM(CASE WHEN tr.is_error = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(tr.tool_use_id)) as failure_rate
        FROM tool_calls tc
        LEFT JOIN tool_results tr ON tc.tool_use_id = tr.tool_use_id
        GROUP BY tc.tool_name
        ORDER BY total_resolved DESC
    """, conn)
    report.append("| Tool Name | Total Execution Results | Error Count | Failure Rate |")
    report.append("| :--- | :--- | :--- | :--- |")
    for _, r in df_failures.iterrows():
        report.append(f"| `{r['tool_name']}` | {r['total_resolved']:,} | {r['failed_count']:,} | {r['failure_rate']:.2f}% |")
    report.append("\n")

    # Numeric Metrics Profiles (Token expenditures and content sizes)
    report.append("## 5. Quantitative Fields & Content Metrics")
    
    # Message content length statistics
    report.append("### Message Text Payload Sizes (`messages.content` character lengths)")
    df_msg_lens = pd.read_sql_query("""
        SELECT MIN(LENGTH(content)) as min_len,
               MAX(LENGTH(content)) as max_len,
               AVG(LENGTH(content)) as avg_len,
               SUM(LENGTH(content)) as total_chars
        FROM messages
    """, conn).iloc[0]
    report.append(f"* **Minimum message size:** {df_msg_lens['min_len']:,} characters")
    report.append(f"* **Maximum message size:** {df_msg_lens['max_len']:,} characters")
    report.append(f"* **Average message size:** {df_msg_lens['avg_len']:,.1f} characters")
    report.append(f"* **Cumulative volume of message strings stored:** {df_msg_lens['total_chars']:,} characters\n")

    # Tool output length statistics
    report.append("### Tool Output Payload Sizes (`tool_results.output_content` character lengths)")
    df_tool_lens = pd.read_sql_query("""
        SELECT tc.tool_name,
               MIN(LENGTH(tr.output_content)) as min_len,
               MAX(LENGTH(tr.output_content)) as max_len,
               AVG(LENGTH(tr.output_content)) as avg_len,
               SUM(LENGTH(tr.output_content)) as total_chars
        FROM tool_calls tc
        JOIN tool_results tr ON tc.tool_use_id = tr.tool_use_id
        GROUP BY tc.tool_name
        ORDER BY avg_len DESC
    """, conn)
    report.append("| Tool Name | Min Length (chars) | Max Length | Avg Length | Cumulative Volume (chars) |")
    report.append("| :--- | :--- | :--- | :--- | :--- |")
    for _, r in df_tool_lens.iterrows():
        report.append(f"| `{r['tool_name']}` | {r['min_len']:,} | {r['max_len']:,} | {r['avg_len']:,.1f} | {r['total_chars']:,} |")
    report.append("\n")

    # Quantiles of Turn Context Metrics
    report.append("### Turn Token Aggregations")
    df_tokens = pd.read_sql_query("""
        SELECT SUM(input_tokens) as total_input,
               SUM(output_tokens) as total_output,
               SUM(cache_read_tokens) as total_cache_read,
               SUM(cache_creation_tokens) as total_cache_create
        FROM events
    """, conn).iloc[0]
    report.append(f"* **Cumulative Non-Cached Input Tokens:** {df_tokens['total_input']:,} tokens")
    report.append(f"* **Cumulative Generated Output Tokens:** {df_tokens['total_output']:,} tokens")
    report.append(f"* **Cumulative Cached Cache Read Tokens:** {df_tokens['total_cache_read']:,} tokens")
    report.append(f"* **Cumulative Cached Cache Creation Tokens:** {df_tokens['total_cache_create']:,} tokens")

    conn.close()

    # Write Markdown file
    output_path = os.path.join("output", "analytics_report.md")
    with open(output_path, "w", encoding="utf-8") as out:
        out.write("\n".join(report))
    print(f"Profiling complete. Report written to {output_path}")

if __name__ == '__main__':
    profile_database()
