# Instructions

## The Claude Analysis Workflow

### Step 0: Clean
If there is already content in `output/` folder, ask user for confirmation to delete it first to start clean.

### Step 1: Ingest & Verify Data
Builds the Docker container, loads all raw session log files into the SQLite database, and runs strict 1:1 relational reconstruction tests to verify zero data loss:
```bash
./load_data.sh
```

For incremental updates, use `--since` to only re-ingest sessions modified after a given timestamp:
```bash
./load_data.sh --since 2026-06-17T10:00:00
```
This skips the full database rebuild and only refreshes the affected sessions.

### Step 2: Run Analytics & Compile Dashboards
Queries the relational database, profiles schema columns, compiles categorical rankings, and generates HTML dashboards and reports:
```bash
./analyze.sh
```

### Step 3: Analyze & Suggest
Review the generated HTML dashboards in `output/` to audit token consumption, identify bottlenecks, and propose optimizations:
* `output/analytics_report.html` — Schema field-level profiling and categorical distributions
* `output/top_10_analytics.html` — Top 10 rankings across sessions, tokens, tools, and payloads

When estimating API costs, use the official pricing at https://platform.claude.com/docs/en/about-claude/pricing — fetch it to get current rates before generating cost reports.

### Step 4: Extend (Custom Queries & New Scripts)
Based on analysis and suggestions:
* Deep-dive into identified problems to understand the core issue and confirm findings based on real data from the database.
* Refer to `output/schema.sql` for the full database schema when writing queries.
* Run custom SQL queries directly:
  ```bash
  ./load_data.sh sqlite3 output/claude_sessions.db
  ```
* Create new analytics scripts and run them:
  ```bash
  ./load_data.sh python3 src/new_script.py
  ```
* Provide solutions.

> **Note:** `load_data.sh` doubles as a Docker wrapper — any positional arguments are passed directly to `docker run` inside the container with the workspace and projects directories mounted.

## More Information
Refer to the main [README.md](README.md) for architecture, directory structure, and execution details.
