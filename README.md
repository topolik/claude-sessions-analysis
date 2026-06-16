# Claude Session Ingestion & Relational Analytics Pipeline

This directory contains a robust, container-native data pipeline designed to parse, verify, profile, and analyze Claude session logs (`*.jsonl` files) utilizing a structured relational SQLite database.

---

## 🚀 The Two-Step Ingestion & Analytics Pipeline

The pipeline is split into two logical steps to isolate database population/verification from downstream analytics and report generation:

### Step 1: Ingest & Verify Data
This step builds the Docker container, loads all raw session log files into the SQLite database, and executes strict 1:1 relational reconstruction tests to mathematically verify that zero data was lost:
```bash
./load_data.sh
```

### Step 2: Run Analytics & Compile Dashboards
This step queries the relational database, profiles schema columns, compiles categorical rankings, and generates publication-grade HTML dashboards and reports:
```bash
./analyze.sh
```

### Step 3: Analyze, Suggest & Extend (Instruction & Deep-Dive Playbook)
Once reports are compiled inside the `output/` folder, use this guide to audit token consumption, apply optimizations, or extend queries to extract deeper behaviors:

#### A. Diagnostic Playbook (How to Analyze & Propose Suggestions)
1. **Locate $O(T^2)$ Bottlenecks:** Open `output/observations.html`. Look for sessions with huge total combined tokens relative to output tokens. If a single session consumes over 100M tokens, it is a candidate for splitting into micro-sessions.
2. **Examine Stuck Tool Loops:** Open `output/top_10_analytics.html`. Review **Category 5 (Tools with Most Failures)**. If `Bash` or `Edit` failure rates are high, inspect the logs of those specific sessions to find looping test suites or linters.
3. **Filter Giant Payloads:** Check **Category 6 & 7 (Largest Message Payloads & Tool Outputs)**. If tool outputs exceed 50,000 characters, enforce quieter logging or output truncation.

#### B. Concrete Developer Action Items (Proposals)
* **Turn-Budget Rule:** Mandate a maximum limit of **50 turns** per session. When a session exceeds this, save the state to `MEMORY.md`, terminate the session, and start a fresh, clean one to save up to 97.0% in cache-reading tokens.
* **Quiet Command Defaults:** When calling `Bash` tools, enforce quiet flags (e.g., `npm test --silent` or `ruff check .`) to keep prompt history compact.
* **Circuit Breakers:** If a command fails 3 times consecutively, stop execution and manually resolve the error locally instead of letting the agent loop.

#### C. Extending the Analytics (Deep-Dive SQL Recipes)
To extend the pipeline and deep-dive into custom metrics, you can run custom SQL queries inside the Docker container using `./load_data.sh sqlite3 output/claude_sessions.db`. Execute these advanced SQL recipes:

##### Recipe 1: Detect Repetitive File Reads
Find sessions reading the exact same file path multiple times via `Read` tool:
```sql
SELECT s.file_path as log_file, json_extract(tc.input_json, '$.file_path') as read_path, COUNT(*) as read_count
FROM tool_calls tc
JOIN events e ON tc.event_row_id = e.row_id
JOIN sessions s ON e.session_id = s.session_id
WHERE tc.tool_name IN ('Read', 'read_file')
GROUP BY log_file, read_path
HAVING read_count > 1
ORDER BY read_count DESC;
```

##### Recipe 2: Calculate Tool Failure Sequences
Identify consecutive failing tool calls to catch looping feedback loops:
```sql
SELECT s.file_path, tc.tool_name, tr.output_content
FROM tool_calls tc
JOIN events e ON tc.event_row_id = e.row_id
JOIN sessions s ON e.session_id = s.session_id
JOIN tool_results tr ON tc.tool_use_id = tr.tool_use_id AND tc.event_row_id = tr.event_row_id
WHERE tr.is_error = 1
ORDER BY s.file_path, e.row_id;
```

##### Recipe 3: Profile Session Cost-to-Activity Efficiency
Calculate how many successful tool calls are achieved per million tokens spent:
```sql
SELECT s.file_path, 
       SUM(CASE WHEN tr.is_error = 0 THEN 1 ELSE 0 END) as successful_calls,
       SUM(e.input_tokens + e.output_tokens) as total_tokens,
       (SUM(CASE WHEN tr.is_error = 0 THEN 1 ELSE 0 END) * 1000000.0) / SUM(e.input_tokens + e.output_tokens) as efficiency_ratio
FROM sessions s
JOIN events e ON s.session_id = e.session_id
LEFT JOIN tool_calls tc ON e.row_id = tc.event_row_id
LEFT JOIN tool_results tr ON tc.tool_use_id = tr.tool_use_id AND tc.event_row_id = tr.event_row_id
GROUP BY s.session_id
HAVING total_tokens > 1000000
ORDER BY efficiency_ratio ASC;
```

---

## 📂 Project Directory Structure

```
/tmp/casd/
├── load_data.sh                 # ⚙️ Step 1 launcher (Loads database & runs lossless verification)
├── analyze.sh                   # 📊 Step 2 launcher (Profiles schema & compiles HTML dashboards)
├── README.md                    # 📖 Project documentation
├── projects/                    # 📂 Raw session log JSONL files (Inputs)
├── output/                      # 📊 All auto-generated DB/HTML files (Strictly isolated!)
│   ├── claude_sessions.db       # Relational SQLite DB (100% losslessly populated)
│   ├── observations.md          # Narrative Token Expenditure Audit Report
│   ├── observations.html         # Narrative Token Expenditure Audit Dashboard
│   ├── analytics_report.md      # Schema profiling metadata report
│   ├── analytics_report.html    # Schema profiling HTML Dashboard
│   ├── top_10_analytics.md      # Multi-category Top 10 rankings report
│   └── top_10_analytics.html    # Multi-category Top 10 rankings Dashboard
└── analytics/                   # ⚙️ All container & Python script sources (Isolated!)
    ├── Dockerfile               # Container environment specification
    ├── professional.css         # Publication-grade HTML stylesheet
    ├── build_database.py        # Database loader engine
    ├── verify_latest_syntax.py  # Schema drift & key syntax evolution validator
    ├── verify_relational_reconstruction.py # 100% Relational reconstruction validator (--all / --latest)
    ├── run_analytics.py         # Schema profiling query module
    └── analyze_top_10.py        # Multi-category rankings query module
```

---

## 🗃️ Generated Assets (Saved in `output/`):

1. **`claude_sessions.db`**: A normalized relational SQLite database storing all sessions, events, tool calls, and content payloads (100% losslessly populated and verified).
2. **`observations.html` / `observations.md`**: A detailed report auditing the workspace's $O(T^2)$ quadratic token expenditure with actionable guidelines for transitioning to micro-sessions for 97.0% cost savings.
3. **`analytics_report.html` / `analytics_report.md`**: A database field-level profiling report tracking column population rates, category value distributions, and token summaries.
4. **`top_10_analytics.html` / `top_10_analytics.md`**: Deep-dive rankings of the top 10 items across key operational categories (longest sessions, highest token costs, active directories, tool frequencies, error rates, large payloads, and turn-by-turn context spikes).
