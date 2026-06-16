#!/bin/bash
set -e

# Resolve current script directory to be absolute and safe
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Ensure the output and source directories exist on the host
mkdir -p output
mkdir -p "$HOME/.claude/projects"

echo "=== STEP 1: Building Docker Image (claude-analytics:latest) ==="
# Build using the Dockerfile inside the src/ folder
docker build -t claude-analytics:latest -f src/Dockerfile src/

# Run a specific command or Python script if an argument is passed
if [ -n "$1" ]; then
  echo "Executing custom command inside container: $*"
  docker run --rm \
    --user "$(id -u):$(id -g)" \
    -v "$SCRIPT_DIR:/workspace" \
    -v "$HOME/.claude/projects:/workspace/projects:ro" \
    claude-analytics:latest \
    "$@"
else
  echo -e "\n=== STEP 2: Ingesting/Updating Relational Database ==="
  docker run --rm \
    --user "$(id -u):$(id -g)" \
    -v "$SCRIPT_DIR:/workspace" \
    -v "$HOME/.claude/projects:/workspace/projects:ro" \
    claude-analytics:latest \
    python3 src/build_database.py

  echo -e "\n=== STEP 3a: Executing Lossless Verification Test Suite (All Sessions) ==="
  docker run --rm \
    --user "$(id -u):$(id -g)" \
    -v "$SCRIPT_DIR:/workspace" \
    -v "$HOME/.claude/projects:/workspace/projects:ro" \
    claude-analytics:latest \
    python3 src/verify_relational_reconstruction.py --all

  echo -e "\n=== STEP 3b: Executing Live Latest Syntax Schema Mapping ==="
  docker run --rm \
    --user "$(id -u):$(id -g)" \
    -v "$SCRIPT_DIR:/workspace" \
    -v "$HOME/.claude/projects:/workspace/projects:ro" \
    claude-analytics:latest \
    python3 src/verify_latest_syntax.py

  echo -e "\n=== STEP 3c: Executing Relational 1:1 Reconstruction Verification (Latest Session) ==="
  docker run --rm \
    --user "$(id -u):$(id -g)" \
    -v "$SCRIPT_DIR:/workspace" \
    -v "$HOME/.claude/projects:/workspace/projects:ro" \
    claude-analytics:latest \
    python3 src/verify_relational_reconstruction.py --latest

  echo -e "\n🎉 Database Ingestion & Lossless Verification Complete!"
fi
