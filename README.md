# Claude Session Ingestion & Relational Analytics Pipeline

A container-native data pipeline that parses, verifies, profiles, and analyzes Claude Code session logs (`~/.claude/projects/*/*.jsonl` files) into a structured relational self-verifying SQLite database.

Use your agent with:
```
Run The 4-Step Workflow and analyze token use. Then answer these questions:

  1. **Where are my tokens going?** Break down total token spend by tool name, session, and event
  type. Show input vs output vs cache_read vs cache_creation ratios. Identify the top 10
  most expensive tool calls and sessions.
  2. **Which tools fail most, and how much do retries cost?** Calculate error rate per tool name.
  For each failed tool call, find the subsequent retry and sum the tokens burned on
  failure+retry pairs. Rank tools by wasted tokens.
  3. **How long are my sessions, and where do they bloat?** For each session, plot event count
  and cumulative token spend. Flag sessions that exceed 50K output tokens or 200 events.
  Identify the event types that contribute most to session bloat.
  4. **What's my cache hit rate, and what kills it?** Calculate cache_read_tokens / input_tokens
  ratio per session and over time. Find sessions or time windows where cache hit rate drops
  below 50%. Correlate cache drops with session length and time gaps between events.
  5. **Which files and tools do I re-read unnecessarily?** Parse input_json from tool_calls where
  tool_name = 'Read' or tool_name = 'Bash' to extract file paths. Find duplicate reads of
  the same path within a session. Rank by wasted tokens on redundant reads.
```

---

## 🚀 Pipeline Workflow

The pipeline is split into steps that isolate database population/verification from downstream analytics and report generation:

### Step 1: Ingest & Verify Data
Builds the Docker container, loads all raw session log files into the SQLite database, and runs strict 1:1 relational reconstruction tests to verify zero data loss:
```bash
./load_data.sh
```

### Step 2: Run Analytics & Compile Dashboards
Queries the relational database, profiles schema columns, compiles categorical rankings, and generates HTML dashboards and reports:
```bash
./analyze.sh
```

### Step 3: Analyze & Suggest
Review the generated reports in `output/` to audit token consumption, identify bottlenecks, and propose optimizations for your Claude Code workflows.

### Step 4: Extend (Deep-Dive & Optimization)
Create new analytics scripts and run them inside the container:
```bash
./load_data.sh python3 src/deep_dive.py
```
Or run custom SQL queries directly:
```bash
./load_data.sh sqlite3 output/claude_sessions.db
```

---

## 📂 Project Directory Structure

```
├── load_data.sh                    # Step 1: Loads database & runs lossless verification
├── analyze.sh                      # Step 2: Profiles schema & compiles HTML dashboards
├── README.md                       # Project documentation
├── AGENT.md                        # AI agent instructions (referenced by CLAUDE.md & GEMINI.md)
├── output/                         # All auto-generated DB/HTML/MD files
│   ├── claude_sessions.db          # Relational SQLite DB (losslessly populated)
│   ├── schema.sql                  # Auto-emitted SQL schema definition
│   ├── observations.{md,html}      # Token expenditure audit report & dashboard
│   ├── analytics_report.{md,html}  # Schema profiling report & dashboard
│   ├── top_10_analytics.{md,html}  # Multi-category Top 10 rankings & dashboard
│   └── solutions/                  # Generated optimization configs & hooks
└── src/                            # Container & Python script sources
    ├── Dockerfile                  # Container environment specification
    ├── professional.css            # HTML stylesheet for dashboards
    ├── build_database.py           # Database loader (dynamic table parsing & schema emission)
    ├── verify_latest_syntax.py     # Schema drift & syntax evolution validator
    ├── verify_relational_reconstruction.py  # Relational reconstruction validator (--all / --latest)
    ├── run_analytics.py            # Schema profiling query module
    ├── analyze_top_10.py           # Multi-category rankings query module
    ├── deep_dive.py                # Cost and efficiency deep-dive analysis
    └── solutions.py                # Optimization action items & solution generator
```

---

## 🗃️ Generated Assets (`output/`)

| File | Description |
|------|-------------|
| `claude_sessions.db` | Normalized relational SQLite database — sessions, events, tool calls, content payloads (losslessly verified) |
| `schema.sql` | Auto-emitted SQL schema definition extracted from the loaded database |
| `observations.{md,html}` | Token expenditure audit report & dashboard |
| `analytics_report.{md,html}` | Schema field-level profiling report & dashboard |
| `top_10_analytics.{md,html}` | Multi-category Top 10 rankings report & dashboard |
| `solutions/` | Generated optimization configs & hooks |
