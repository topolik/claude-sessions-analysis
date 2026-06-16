#!/bin/bash
set -e

# Resolve current script directory to be absolute and safe
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Ensure the output directory exists on the host
mkdir -p output

echo "=== STEP 1: Building Docker Image (claude-analytics:latest) ==="
# Build using the Dockerfile inside the analytics/ folder
docker build -t claude-analytics:latest -f analytics/Dockerfile analytics/

# Run a specific command or Python script if an argument is passed
if [ -n "$1" ]; then
  echo "Executing custom command inside container: $@"
  docker run --rm \
    --user "$(id -u):$(id -g)" \
    -v "$SCRIPT_DIR:/workspace" \
    claude-analytics:latest \
    "$@"
else
  # Default full end-to-end containerized analytics sequence
  echo -e "\n=== STEP 2: Ingesting/Updating Relational Database ==="
  docker run --rm \
    --user "$(id -u):$(id -g)" \
    -v "$SCRIPT_DIR:/workspace" \
    claude-analytics:latest \
    python3 analytics/build_database.py

  echo -e "\n=== STEP 3: Executing Lossless Verification Test Suite ==="
  docker run --rm \
    --user "$(id -u):$(id -g)" \
    -v "$SCRIPT_DIR:/workspace" \
    claude-analytics:latest \
    python3 analytics/verify_data_lossless.py

  echo -e "\n=== STEP 3b: Executing Live Latest Syntax Schema Mapping ==="
  docker run --rm \
    --user "$(id -u):$(id -g)" \
    -v "$SCRIPT_DIR:/workspace" \
    claude-analytics:latest \
    python3 analytics/verify_latest_syntax.py

  echo -e "\n=== STEP 3c: Executing Relational 1:1 Reconstruction Verification ==="
  docker run --rm \
    --user "$(id -u):$(id -g)" \
    -v "$SCRIPT_DIR:/workspace" \
    claude-analytics:latest \
    python3 analytics/verify_relational_reconstruction.py

  echo -e "\n=== STEP 4: Generating Schema Field-Level Usage Profile ==="
  docker run --rm \
    --user "$(id -u):$(id -g)" \
    -v "$SCRIPT_DIR:/workspace" \
    claude-analytics:latest \
    python3 analytics/run_analytics.py

  echo -e "\n=== STEP 5: Generating Multi-Category Top 10 Rank Deep Dive ==="
  docker run --rm \
    --user "$(id -u):$(id -g)" \
    -v "$SCRIPT_DIR:/workspace" \
    claude-analytics:latest \
    python3 analytics/analyze_top_10.py

  # Containerized compilation of compiled reports to elegant HTML using pandoc
  echo -e "\n=== STEP 6: Compiling Markdown Reports to Professional HTML (Inside Container) ==="
  docker run --rm \
    --user "$(id -u):$(id -g)" \
    -v "$SCRIPT_DIR:/workspace" \
    claude-analytics:latest \
    sh -c "pandoc --standalone --mathjax --css=analytics/professional.css -o output/analytics_report.html output/analytics_report.md && pandoc --standalone --mathjax --css=analytics/professional.css -o output/top_10_analytics.html output/top_10_analytics.md && pandoc --standalone --mathjax --css=analytics/professional.css -o output/observations.html output/observations.md"
  
  echo "  -> Compiled: output/analytics_report.html"
  echo "  -> Compiled: output/top_10_analytics.html"
  echo "  -> Compiled: output/observations.html"
  
  echo -e "\n🎉 End-to-End Containerized Ingestion & Analytics Pipeline Complete!"
fi
