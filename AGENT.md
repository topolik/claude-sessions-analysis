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
Review the generated reports in `output/` to audit token consumption, identify bottlenecks, and propose optimizations for your Claude Code workflows.

### Step 4: Extend (Deep-Dive & Optimization)
Based on analysis and suggestions:
* Run custom SQL queries directly:
  ```bash
  ./load_data.sh sqlite3 output/claude_sessions.db
  ```
* Deep-dive into identified problems to understand the core issue.
* Confirm findings based on real data from the database.
* Create new analytics scripts and run them:
  ```bash
  ./load_data.sh python3 src/new_script.py
  ```
* Provide solutions.

## More Information
Refer to the main [README.md](README.md) for architecture, directory structure, and execution details.
