#!/bin/bash
set -e

# Resolve current script directory to be absolute and safe
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Ensure the database exists before running analysis
if [ ! -f "output/claude_sessions.db" ]; then
  echo "Error: Database output/claude_sessions.db not found!"
  echo "Please run the ingestion step first: ./load_data.sh"
  exit 1
fi

# Ensure the analytics image exists (analyze.sh may be run independently of load_data.sh)
echo "=== Building Docker Image (claude-analytics:latest) ==="
docker build -t claude-analytics:latest -f src/Dockerfile src/

echo -e "\n=== STEP 1: Generating Schema Field-Level Usage Profile ==="
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "$SCRIPT_DIR:/workspace" \
  claude-analytics:latest \
  python3 src/run_analytics.py

echo -e "\n=== STEP 2: Generating Multi-Category Top 10 Rank Deep Dive ==="
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "$SCRIPT_DIR:/workspace" \
  claude-analytics:latest \
  python3 src/analyze_top_10.py

# Containerized compilation of compiled reports to elegant HTML using pandoc
echo -e "\n=== STEP 3: Compiling Markdown Reports to Professional HTML (Inside Container) ==="
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "$SCRIPT_DIR:/workspace" \
  claude-analytics:latest \
  sh -c "pandoc --standalone --metadata title=\"Claude Session Analytics & Schema Profile\" --mathjax --css=src/professional.css -o output/analytics_report.html output/analytics_report.md && pandoc --standalone --metadata title=\"Multi-Category Top 10 Deep Dive\" --mathjax --css=src/professional.css -o output/top_10_analytics.html output/top_10_analytics.md"

echo "  -> Compiled: output/analytics_report.html"
echo "  -> Compiled: output/top_10_analytics.html"

echo -e "\n🎉 Downstream Analytical Reports & Dashboards Compiled Successfully!"
