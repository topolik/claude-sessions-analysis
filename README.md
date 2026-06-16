# Claude Session Ingestion & Relational Analytics Pipeline

This directory contains a robust, container-native data pipeline designed to parse, verify, profile, and analyze Claude session logs (`*.jsonl` files) utilizing a structured relational SQLite database.

---

## 🚀 The Consolidated Ingestion & Analytics Pipeline

The workspace root contains an end-to-end containerized pipeline that processes all **514 files (110,904 events)** into a queryable relational database, runs lossless fidelity tests, profiles database columns, compiles analytics rankings, and outputs publication-grade HTML dashboards.

**The ONLY requirement on the host system is Docker.** To build, ingest, and compile all dashboards, run:
```bash
./run.sh
```

---

## 📂 Project Directory Structure

```
/tmp/casd/
├── run.sh                       # 🚀 Root entrypoint (Executes the whole pipeline)
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
    ├── verify_data_lossless.py  # 100% Exhaustive semantic lossless test
    ├── run_analytics.py         # Schema profiling query module
    └── analyze_top_10.py        # Multi-category rankings query module
```

---

## 🗃️ Generated Assets (Saved in `output/`):

1. **`claude_sessions.db`**: A normalized relational SQLite database storing all sessions, events, tool calls, and content payloads (100% losslessly populated and verified).
2. **`observations.html` / `observations.md`**: A detailed report auditing the workspace's $O(T^2)$ quadratic token expenditure with actionable guidelines for transitioning to micro-sessions for 97.0% cost savings.
3. **`analytics_report.html` / `analytics_report.md`**: A database field-level profiling report tracking column population rates, category value distributions, and token summaries.
4. **`top_10_analytics.html` / `top_10_analytics.md`**: Deep-dive rankings of the top 10 items across key operational categories (longest sessions, highest token costs, active directories, tool frequencies, error rates, large payloads, and turn-by-turn context spikes).
