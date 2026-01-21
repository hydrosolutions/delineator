#!/bin/bash
# Ralph Wiggum - Long-running AI agent loop
# Usage: ./ralph.sh [prd_file] [max_iterations]
#
# Examples:
#   ./ralph.sh                          # uses prd.md, 10 iterations
#   ./ralph.sh 20                       # uses prd.md, 20 iterations
#   ./ralph.sh tasks/prd-feature.md     # uses custom prd, 10 iterations
#   ./ralph.sh tasks/prd-feature.md 20  # uses custom prd, 20 iterations

set -e

# Parse arguments - first arg can be a .md file or a number
if [[ "$1" =~ \.md$ ]]; then
  PRD_FILE="$1"
  MAX_ITERATIONS=${2:-10}
elif [[ "$1" =~ ^[0-9]+$ ]]; then
  PRD_FILE="prd.md"
  MAX_ITERATIONS=${1:-10}
else
  PRD_FILE="prd.md"
  MAX_ITERATIONS=${1:-10}
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# If PRD_FILE is relative, make it relative to current working directory
if [[ ! "$PRD_FILE" = /* ]]; then
  PRD_FILE="$(pwd)/$PRD_FILE"
fi

# Derive progress file from PRD file (prd-feature.md -> progress-feature.txt)
PRD_BASENAME="$(basename "$PRD_FILE" .md)"
FEATURE_NAME="${PRD_BASENAME#prd-}"
PROGRESS_FILE="$(dirname "$PRD_FILE")/progress-${FEATURE_NAME}.txt"
ARCHIVE_DIR="$SCRIPT_DIR/archive"
LAST_BRANCH_FILE="$SCRIPT_DIR/.last-branch"

# Helper function to extract branchName from YAML frontmatter in markdown
extract_branch_name() {
  local file="$1"
  # Extract YAML frontmatter (between --- markers) and find branchName
  sed -n '/^---$/,/^---$/p' "$file" 2>/dev/null | grep -E '^branchName:' | sed 's/branchName:[[:space:]]*//' | tr -d '"' | tr -d "'"
}

# Archive previous run if branch changed
if [ -f "$PRD_FILE" ] && [ -f "$LAST_BRANCH_FILE" ]; then
  CURRENT_BRANCH=$(extract_branch_name "$PRD_FILE")
  LAST_BRANCH=$(cat "$LAST_BRANCH_FILE" 2>/dev/null || echo "")

  if [ -n "$CURRENT_BRANCH" ] && [ -n "$LAST_BRANCH" ] && [ "$CURRENT_BRANCH" != "$LAST_BRANCH" ]; then
    # Archive the previous run
    DATE=$(date +%Y-%m-%d)
    # Strip "ralph/" prefix from branch name for folder
    FOLDER_NAME=$(echo "$LAST_BRANCH" | sed 's|^ralph/||')
    ARCHIVE_FOLDER="$ARCHIVE_DIR/$DATE-$FOLDER_NAME"

    echo "Archiving previous run: $LAST_BRANCH"
    mkdir -p "$ARCHIVE_FOLDER"
    [ -f "$PRD_FILE" ] && cp "$PRD_FILE" "$ARCHIVE_FOLDER/"
    [ -f "$PROGRESS_FILE" ] && cp "$PROGRESS_FILE" "$ARCHIVE_FOLDER/"
    echo "   Archived to: $ARCHIVE_FOLDER"

    # Reset progress file for new run
    echo "# Ralph Progress Log" > "$PROGRESS_FILE"
    echo "Started: $(date)" >> "$PROGRESS_FILE"
    echo "---" >> "$PROGRESS_FILE"
  fi
fi

# Track current branch
if [ -f "$PRD_FILE" ]; then
  CURRENT_BRANCH=$(extract_branch_name "$PRD_FILE")
  if [ -n "$CURRENT_BRANCH" ]; then
    echo "$CURRENT_BRANCH" > "$LAST_BRANCH_FILE"
  fi
fi

# Initialize progress file if it doesn't exist
if [ ! -f "$PROGRESS_FILE" ]; then
  echo "# Ralph Progress Log" > "$PROGRESS_FILE"
  echo "Started: $(date)" >> "$PROGRESS_FILE"
  echo "---" >> "$PROGRESS_FILE"
fi

echo "Starting Ralph - Max iterations: $MAX_ITERATIONS"

for i in $(seq 1 $MAX_ITERATIONS); do
  echo ""
  echo "═══════════════════════════════════════════════════════"
  echo "  Ralph Iteration $i of $MAX_ITERATIONS"
  echo "═══════════════════════════════════════════════════════"
  
  # Build the prompt with actual file paths
  PROMPT="# File Paths for This Run
PRD_FILE: $PRD_FILE
PROGRESS_FILE: $PROGRESS_FILE

$(cat "$SCRIPT_DIR/prompt.md")"

  # Run claude with the ralph prompt
  OUTPUT=$(claude --dangerously-skip-permissions -p "$PROMPT" 2>&1 | tee /dev/stderr) || true
  
  # Check for completion signal
  if echo "$OUTPUT" | grep -q "<promise>COMPLETE</promise>"; then
    echo ""
    echo "═══════════════════════════════════════════════════════"
    echo "  ✓ Ralph completed all tasks and merged to main!"
    echo "═══════════════════════════════════════════════════════"
    echo "Completed at iteration $i of $MAX_ITERATIONS"
    exit 0
  fi

  # Check for merge conflict signal
  if echo "$OUTPUT" | grep -q "<promise>MERGE_CONFLICT</promise>"; then
    echo ""
    echo "═══════════════════════════════════════════════════════"
    echo "  ⚠ Ralph encountered merge conflicts!"
    echo "═══════════════════════════════════════════════════════"
    echo "All stories are complete, but main has diverged."
    echo "Please resolve conflicts manually:"
    echo "  1. git checkout main && git pull"
    echo "  2. git merge <feature-branch>"
    echo "  3. Resolve conflicts"
    echo "  4. git push origin main"
    exit 2
  fi

  # Check for story completion signal
  if echo "$OUTPUT" | grep -q "<promise>STORY_COMPLETE</promise>"; then
    echo "  ✓ Story completed. Starting next iteration..."
  else
    echo "  Iteration $i ended without completion signal."
  fi
  sleep 2
done

echo ""
echo "Ralph reached max iterations ($MAX_ITERATIONS) without completing all tasks."
echo "Check $PROGRESS_FILE for status."
exit 1
