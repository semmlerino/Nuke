#!/usr/bin/bash

# Background script to push encoded bundle to encoded-releases branch
# Called by post-commit hook, runs independently

# Get project root
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LOG_FILE="$PROJECT_ROOT/.post-commit-output/bundle-push.log"

# Wait for git to finish the commit
sleep 3

# Start logging
echo "[$(date)] Starting background bundle push..." > "$LOG_FILE"

# Get current branch (saved before hook exits)
CURRENT_BRANCH=$(cat "$PROJECT_ROOT/.post-commit-output/current_branch.txt" 2>/dev/null || echo "master")
COMMIT_MSG=$(cat "$PROJECT_ROOT/.post-commit-output/commit_msg.txt" 2>/dev/null || echo "Unknown commit")
CURRENT_COMMIT=$(cat "$PROJECT_ROOT/.post-commit-output/current_commit.txt" 2>/dev/null || echo "unknown")

echo "Original branch: $CURRENT_BRANCH" >> "$LOG_FILE"
echo "Original commit: $CURRENT_COMMIT" >> "$LOG_FILE"
echo "Commit message: $COMMIT_MSG" >> "$LOG_FILE"

# Check if bundle exists
if [ ! -f "$PROJECT_ROOT/encoded_releases/shotbot_latest.txt" ]; then
    echo "ERROR: shotbot_latest.txt not found" >> "$LOG_FILE"
    exit 1
fi

# Copy bundle to temp location BEFORE switching branches
TEMP_DIR="/tmp/shotbot_bundle_$$"
mkdir -p "$TEMP_DIR"
echo "Copying bundle to temp location: $TEMP_DIR" >> "$LOG_FILE"
cp "$PROJECT_ROOT/encoded_releases/shotbot_latest.txt" "$TEMP_DIR/shotbot_latest.txt" 2>> "$LOG_FILE"
cp "$PROJECT_ROOT/encoded_releases/shotbot_latest_metadata.json" "$TEMP_DIR/shotbot_latest_metadata.json" 2>> "$LOG_FILE"

# Navigate to project root
cd "$PROJECT_ROOT"

# Save current state (in case there are uncommitted changes)
echo "Saving current state..." >> "$LOG_FILE"
git stash -q --include-untracked 2>> "$LOG_FILE" || true

# Switch to encoded-releases branch
echo "Switching to encoded-releases branch..." >> "$LOG_FILE"
if git show-ref --verify --quiet refs/heads/encoded-releases; then
    git checkout -q encoded-releases 2>> "$LOG_FILE"
else
    # Try to fetch from remote first
    git fetch -q origin encoded-releases 2>> "$LOG_FILE" || true
    if git show-ref --verify --quiet refs/remotes/origin/encoded-releases; then
        git checkout -q -b encoded-releases origin/encoded-releases 2>> "$LOG_FILE"
    else
        # Create orphan branch if it doesn't exist anywhere
        git checkout -q --orphan encoded-releases 2>> "$LOG_FILE"
    fi
fi

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to switch to encoded-releases branch" >> "$LOG_FILE"
    git checkout -q "$CURRENT_BRANCH" 2>> "$LOG_FILE"
    git stash pop -q 2>/dev/null || true
    exit 1
fi

# On encoded-releases branch now - just copy the bundle files (overwrites existing)
echo "Copying bundle files from temp..." >> "$LOG_FILE"
cp "$TEMP_DIR/shotbot_latest.txt" shotbot_latest.txt 2>> "$LOG_FILE"
cp "$TEMP_DIR/shotbot_latest_metadata.json" shotbot_latest_metadata.json 2>> "$LOG_FILE"

if [ ! -f "shotbot_latest.txt" ]; then
    echo "ERROR: Failed to copy bundle files" >> "$LOG_FILE"
    rm -rf "$TEMP_DIR"
    git checkout -q "$CURRENT_BRANCH" 2>> "$LOG_FILE"
    git stash pop -q 2>/dev/null || true
    exit 1
fi

# Update metadata with commit info (ensures file changes on every commit)
echo "Updating metadata with commit info..." >> "$LOG_FILE"
python3 -c "
import json
import sys
from datetime import datetime

try:
    with open('shotbot_latest_metadata.json', 'r') as f:
        metadata = json.load(f)

    metadata['source_commit'] = '$CURRENT_COMMIT'
    metadata['source_branch'] = '$CURRENT_BRANCH'
    metadata['bundle_timestamp'] = datetime.utcnow().isoformat() + 'Z'

    with open('shotbot_latest_metadata.json', 'w') as f:
        json.dump(metadata, f, indent=2)

    print('✓ Metadata updated')
except Exception as e:
    print(f'⚠ Failed to update metadata: {e}', file=sys.stderr)
    sys.exit(1)
" >> "$LOG_FILE" 2>&1

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to update metadata" >> "$LOG_FILE"
    rm -rf "$TEMP_DIR"
    git checkout -q "$CURRENT_BRANCH" 2>> "$LOG_FILE"
    git stash pop -q 2>/dev/null || true
    exit 1
fi

# Add and commit
echo "Adding files to git..." >> "$LOG_FILE"
git add shotbot_latest.txt shotbot_latest_metadata.json 2>> "$LOG_FILE"

# Create commit message
SHORT_COMMIT=$(echo $CURRENT_COMMIT | cut -c1-7)
COMMIT_MESSAGE="Auto-encoded release for commit $SHORT_COMMIT

Original commit: $COMMIT_MSG

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"

echo "Creating commit..." >> "$LOG_FILE"
git commit -q -m "$COMMIT_MESSAGE" 2>> "$LOG_FILE"

if [ $? -ne 0 ]; then
    echo "WARNING: Commit failed (possibly no changes)" >> "$LOG_FILE"
fi

# Push to remote
echo "Pushing to origin/encoded-releases..." >> "$LOG_FILE"
git push -q origin encoded-releases >> "$LOG_FILE" 2>&1
PUSH_EXIT=$?

if [ $PUSH_EXIT -eq 0 ]; then
    echo "✓ Successfully pushed to origin/encoded-releases" >> "$LOG_FILE"
    echo "✓ SUCCESS" >> "$LOG_FILE"
else
    echo "⚠ Failed to push to origin/encoded-releases (exit code: $PUSH_EXIT)" >> "$LOG_FILE"
    echo "✗ FAILED" >> "$LOG_FILE"
fi

# Switch back to original branch
echo "Switching back to $CURRENT_BRANCH..." >> "$LOG_FILE"

# Remove any post-commit-output files that might conflict
# (These are output files that get regenerated on every commit)
rm -f "$PROJECT_ROOT/.post-commit-output/"*.txt 2>> "$LOG_FILE" || true

git checkout -q "$CURRENT_BRANCH" 2>> "$LOG_FILE"
CHECKOUT_EXIT=$?

if [ $CHECKOUT_EXIT -ne 0 ]; then
    echo "ERROR: Failed to switch back to $CURRENT_BRANCH" >> "$LOG_FILE"
    echo "Attempting force checkout..." >> "$LOG_FILE"
    git checkout -qf "$CURRENT_BRANCH" 2>> "$LOG_FILE" || true
fi

# Restore stashed changes
git stash pop -q 2>> "$LOG_FILE" || true

# Clean up temp directory
echo "Cleaning up temp files..." >> "$LOG_FILE"
rm -rf "$TEMP_DIR"

echo "[$(date)] Background bundle push completed" >> "$LOG_FILE"

exit 0
