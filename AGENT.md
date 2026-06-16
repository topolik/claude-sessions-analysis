# Instructions

## The 4-Step Workflow

### Step 1: Ingest and Verify Data
```bash
./load_data.sh
```

### Step 2: Run Analytics and Compile Reports
```bash
./analyze.sh
```

### Step 3: Analyze and Suggest
Review the generated reports in `output/` to audit token consumption, identify bottlenecks, and propose optimizations.

### Step 4: Extend (Optimization)
Based on analysis and suggestions:
* Deep-dive into identified problems to understand the core issue.
* Create new analytics scripts and run them:
  ```bash
  ./load_data.sh python3 analytics/new_script.py
  ```
* Confirm findings based on real data from the database.
* Provide solutions.

## More Information
Refer to the main [README.md](README.md) for architecture, directory structure, and execution details.
