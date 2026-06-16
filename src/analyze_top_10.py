import os
import sqlite3
import pandas as pd

def table_and_cols_exist(conn, table, cols):
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    if not cursor.fetchone():
        return False
    cursor.execute(f"PRAGMA table_info([{table}])")
    existing = {col[1] for col in cursor.fetchall()}
    return all(c in existing for c in cols)

def run_top_10_analytics():
    db_path = os.path.join("output", "claude_sessions.db")
    if not os.path.exists(db_path):
        print(f"Error: Database {db_path} does not exist.")
        exit(1)

    conn = sqlite3.connect(db_path)
    
    report = []
    report.append("# Multi-Category Analytics: Top 10 Deep Dive\n")
    report.append("This report lists the Top 10 entries across key database categories to pinpoint cost drivers, structural bottlenecks, massive payloads, and project activity hotspots.\n")

    # Category 1: Top 10 Sessions by Event/Turn Count
    if table_and_cols_exist(conn, "sessions", ["session_id", "file_path"]) and table_and_cols_exist(conn, "events", ["row_id", "session_id"]):
        report.append("## Category 1: Top 10 Sessions by Total Turn/Event Count")
        df_turns = pd.read_sql_query("""
            SELECT s.file_path, COUNT(e.row_id) as turns 
            FROM sessions s 
            JOIN events e ON s.session_id = e.session_id 
            GROUP BY s.session_id 
            ORDER BY turns DESC 
            LIMIT 10
        """, conn)
        report.append("| Rank | File Path | Total Event Rows |")
        report.append("| :--- | :--- | :--- |")
        for idx, r in df_turns.iterrows():
            report.append(f"| {idx+1} | `{r['file_path']}` | {r['turns']:,} |")
        report.append("\n")

    # Category 2: Top 10 Sessions by Total Combined Tokens
    if table_and_cols_exist(conn, "sessions", ["session_id", "file_path"]) and table_and_cols_exist(conn, "events", ["session_id", "input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens"]):
        report.append("## Category 2: Top 10 Sessions by Total Combined Tokens")
        df_tokens = pd.read_sql_query("""
            SELECT s.file_path, 
                   SUM(e.input_tokens + e.output_tokens + e.cache_read_tokens + e.cache_creation_tokens) as total,
                   SUM(e.input_tokens) as input,
                   SUM(e.output_tokens) as output,
                   SUM(e.cache_read_tokens) as cache_read,
                   SUM(e.cache_creation_tokens) as cache_create
            FROM sessions s
            JOIN events e ON s.session_id = e.session_id
            GROUP BY s.session_id
            ORDER BY total DESC
            LIMIT 10
        """, conn)
        report.append("| Rank | File Path | Total Combined Tokens | Non-Cached Input | Output | Cache Read | Cache Create |")
        report.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for idx, r in df_tokens.iterrows():
            report.append(f"| {idx+1} | `{r['file_path']}` | **{r['total']:,}** | {r['input']:,} | {r['output']:,} | {r['cache_read']:,} | {r['cache_create']:,} |")
        report.append("\n")

    # Category 3: Top 10 Most Active Projects (by Session Log Counts)
    if table_and_cols_exist(conn, "sessions", ["file_path"]):
        report.append("## Category 3: Top 10 Most Active Projects (by Session Log Counts)")
        df_projects = pd.read_sql_query("""
            SELECT file_path FROM sessions
        """, conn)
        
        # Parse folder name from paths
        project_counts = {}
        for _, r in df_projects.iterrows():
            parts = r['file_path'].split('/')
            if len(parts) > 1:
                proj = parts[1]
                project_counts[proj] = project_counts.get(proj, 0) + 1
                
        sorted_projs = sorted(project_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        report.append("| Rank | Project / Directory Name | Number of Session Logs |")
        report.append("| :--- | :--- | :--- |")
        for idx, (proj, count) in enumerate(sorted_projs):
            report.append(f"| {idx+1} | `{proj}` | {count:,} |")
        report.append("\n")

    # Category 4: Top 10 Most Frequently Used Tools
    if table_and_cols_exist(conn, "tool_calls", ["tool_name"]):
        report.append("## Category 4: Top 10 Most Frequently Used Tools")
        df_tools = pd.read_sql_query("""
            SELECT tool_name, COUNT(*) as count 
            FROM tool_calls 
            GROUP BY tool_name 
            ORDER BY count DESC 
            LIMIT 10
        """, conn)
        report.append("| Rank | Tool Name | Invocation Count |")
        report.append("| :--- | :--- | :--- |")
        for idx, r in df_tools.iterrows():
            report.append(f"| {idx+1} | `{r['tool_name']}` | {r['count']:,} |")
        report.append("\n")

    # Category 5: Top 10 Tools with Most Failures
    if table_and_cols_exist(conn, "tool_calls", ["tool_name", "tool_use_id"]) and table_and_cols_exist(conn, "tool_results", ["tool_use_id", "is_error"]):
        report.append("## Category 5: Top 10 Tools with Most Failures")
        df_failed = pd.read_sql_query("""
            SELECT tc.tool_name, 
                   COUNT(tr.tool_use_id) as total,
                   SUM(CASE WHEN tr.is_error = 1 THEN 1 ELSE 0 END) as failures,
                   (SUM(CASE WHEN tr.is_error = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(tr.tool_use_id)) as failure_rate
            FROM tool_calls tc
            JOIN tool_results tr ON tc.tool_use_id = tr.tool_use_id
            GROUP BY tc.tool_name
            ORDER BY failures DESC
            LIMIT 10
        """, conn)
        report.append("| Rank | Tool Name | Total Executions | Failed Runs | Failure Rate |")
        report.append("| :--- | :--- | :--- | :--- | :--- |")
        for idx, r in df_failed.iterrows():
            report.append(f"| {idx+1} | `{r['tool_name']}` | {r['total']:,} | {r['failures']:,} | {r['failure_rate']:.2f}% |")
        report.append("\n")

    # Category 6: Top 10 Largest Message Payloads
    if table_and_cols_exist(conn, "messages", ["content", "event_row_id"]) and table_and_cols_exist(conn, "events", ["row_id", "session_id", "event_type", "role"]) and table_and_cols_exist(conn, "sessions", ["session_id", "file_path"]):
        report.append("## Category 6: Top 10 Largest Message Payloads")
        df_msg = pd.read_sql_query("""
            SELECT s.file_path, e.event_type, e.role, LENGTH(m.content) as length, SUBSTR(m.content, 1, 100) as snippet
            FROM messages m
            JOIN events e ON m.event_row_id = e.row_id
            JOIN sessions s ON e.session_id = s.session_id
            ORDER BY length DESC
            LIMIT 10
        """, conn)
        report.append("| Rank | File Path | Event Type | Role | Content Length (chars) | Message Snippet |")
        report.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for idx, r in df_msg.iterrows():
            snippet = r['snippet'].replace('\n', ' ').replace('|', '\\|')
            report.append(f"| {idx+1} | `{r['file_path']}` | `{r['event_type']}` | `{r['role']}` | {r['length']:,} | {snippet}... |")
        report.append("\n")

    # Category 7: Top 10 Largest Tool Outputs
    if table_and_cols_exist(conn, "tool_results", ["output_content", "tool_use_id", "event_row_id"]) and table_and_cols_exist(conn, "tool_calls", ["tool_use_id", "tool_name"]) and table_and_cols_exist(conn, "events", ["row_id", "session_id"]) and table_and_cols_exist(conn, "sessions", ["session_id", "file_path"]):
        report.append("## Category 7: Top 10 Largest Tool Outputs")
        df_tool_output = pd.read_sql_query("""
            SELECT s.file_path, tc.tool_name, LENGTH(tr.output_content) as length, SUBSTR(tr.output_content, 1, 100) as snippet
            FROM tool_results tr
            JOIN tool_calls tc ON tr.tool_use_id = tc.tool_use_id
            JOIN events e ON tr.event_row_id = e.row_id
            JOIN sessions s ON e.session_id = s.session_id
            ORDER BY length DESC
            LIMIT 10
        """, conn)
        report.append("| Rank | File Path | Tool Name | Output Length (chars) | Output Snippet |")
        report.append("| :--- | :--- | :--- | :--- | :--- |")
        for idx, r in df_tool_output.iterrows():
            snippet = r['snippet'].replace('\n', ' ').replace('|', '\\|')
            report.append(f"| {idx+1} | `{r['file_path']}` | `{r['tool_name']}` | {r['length']:,} | {snippet}... |")
            report.append("\n")

    # Category 8: Top 10 Single-Turn Token Bursts
    if table_and_cols_exist(conn, "events", ["session_id", "event_type", "input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens"]) and table_and_cols_exist(conn, "sessions", ["session_id", "file_path"]):
        report.append("## Category 8: Top 10 Single-Turn Token Bursts")
        df_bursts = pd.read_sql_query("""
            SELECT s.file_path, e.event_type, 
                   (e.input_tokens + e.output_tokens + e.cache_read_tokens + e.cache_creation_tokens) as turn_total,
                   e.input_tokens, e.output_tokens, e.cache_read_tokens, e.cache_creation_tokens
            FROM events e
            JOIN sessions s ON e.session_id = s.session_id
            ORDER BY turn_total DESC
            LIMIT 10
        """, conn)
        report.append("| Rank | File Path | Event Type | Total Turn Tokens | Non-Cached Input | Output | Cache Read | Cache Create |")
        report.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for idx, r in df_bursts.iterrows():
            report.append(f"| {idx+1} | `{r['file_path']}` | `{r['event_type']}` | **{r['turn_total']:,}** | {r['input_tokens']:,} | {r['output_tokens']:,} | {r['cache_read_tokens']:,} | {r['cache_creation_tokens']:,} |")

    conn.close()

    # Save to top_10_analytics.md
    output_path = os.path.join("output", "top_10_analytics.md")
    with open(output_path, "w", encoding="utf-8") as out:
        out.write("\n".join(report))
    print(f"Top 10 deep dive completed. Report written to {output_path}")

if __name__ == '__main__':
    run_top_10_analytics()
