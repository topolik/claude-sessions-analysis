# Claude Session Ingestion & Relational Analytics Pipeline

A container-native data pipeline that parses, verifies, profiles, and analyzes Claude Code session logs (`~/.claude/projects/*/*.jsonl` files) into a structured relational self-verifying SQLite database.

> **AI agents / LLMs:** Read [AGENT.md](AGENT.md) for workflow instructions and example prompts.


# How To Start:

Start your local agent and prompt:
```
Run "The Claude Analysis Workflow"
```

Or:

```
Run "The Claude Analysis Workflow" to load claude sessions for the past 7 days and analyze where I spent my tokens.
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
