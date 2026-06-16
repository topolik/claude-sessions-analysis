# Instructions

## The 4 Step Workflow

Perform the whole 4-step workflow:

### Step 1: Ingest and Verify Data
```bash
./load_data.sh
```

### Step 2: Run Analytics and Compile Reports
```bash
./analyze.sh
```

### Step 3: Analyze, Suggest
Refer to the main [README.md](README.md#step-3-analyze-suggest--extend-instruction--deep-dive-playbook) for detailed guidelines on:
* **Diagnostic Playbooks:** Spotting $O(T^2)$ bottlenecks, tool failures, and massive log payloads.
* **Proposals & Actions:** Limiting session turn budgets, silencing command verbose dumps, and setting circuit breakers.
* **Advanced SQL Recipes:** Custom SQLite queries to extract repetitive reads, consecutive loop failures, and cost-to-activity efficiency ratios.

### Step 4: Extend (Optimization)
Based on analysis and suggestions:
* Deep-dive into identified problems to understand the core issue
* Create new analytics scripts and run them using `./run.sh python3 analytics/new_script.py`.
* Confirm the findings based on real data from the database
* Provide solution


## More Information
Please refer to the main repository [README.md](README.md) for the architecture, guidelines, directory structure, and execution instructions.
