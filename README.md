# Claude Session Ingestion & Relational Analytics Pipeline

A container-native data pipeline that parses, verifies, profiles, and analyzes Claude Code session logs (`~/.claude/projects/*/*.jsonl` files) into a structured relational self-verifying SQLite database.

Use your agent with:
```
Run The 4-Step Workflow and analyze token use.
```

Then:
```
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

Or

```
  1. **What's my ROI per session** — which sessions produce real work vs. just burn tokens?
  
  We know cost per session but not value. Correlate token spend against actual artifacts
  produced: Edit/Write calls that succeed, lines changed, files created. Sessions with 7K
  events but low edit counts are pure exploration waste. This gives you a "cost per useful
  edit" metric to benchmark against.

  2. Which tool call sequences predict failure — and can I short-circuit them?

  We counted errors per tool, but not the chains leading to them. Are there recurring
  patterns like Edit→fail→Read→Edit→succeed or Bash→Bash→Bash→fail→Bash→fail→give up?
  Identifying 3-4 step anti-patterns lets you write hooks or instructions that break the loop
  early.

  3. What's the real cost of subagents vs. inline work, and are they being spawned at the 
  right model tier?

  Many Agent calls appeared, but we never unpacked what model they ran, how many tokens they
  consumed downstream (the child sessions), or whether the work could have been done inline.
  Does your CLAUDE.md has explicit model routing rules (haiku for explore, sonnet for codegen,
  opus for security)? Are those being followed? Misrouted subagents are the silent budget
  killer.

  4. How does context size grow within a session, and where are the compaction cliffs?

  Cache creation spikes signal context rebuilds — either from /compact, context overflow, or
  cache TTL expiry. Plotting cache_creation_tokens as a time series within each long session
  shows exactly when context gets rebuilt and how much it costs each time. The monster
  sessions likely have repeated compaction cycles that each cost 5-10M tokens. Knowing the
  optimal turn count before compaction saves you from both extremes: compacting too early
  (wasted cache warmth) and too late (context overflow).

  5. When do I work, and does my token efficiency change across the day/week?

  The timestamp data is sitting unused. Token efficiency (output per cache-read, edits per
  turn) likely varies by time of day and session age. Late-night sessions or Friday
  afternoons might show higher error rates, more redundant reads, or longer tool chains. This
  isn't just curiosity — it tells you when to trust the agent with autonomous work vs. when
  to keep it on a shorter leash.
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
