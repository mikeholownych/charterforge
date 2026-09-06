#!/usr/bin/env bash
# Sync upstream/main into this fork
# Run from repo root: ./scripts/sync-upstream.sh

set -euo pipefail

echo "=== Syncing upstream/main ==="
git fetch upstream

# Show what's new
echo "New commits on upstream/main since last sync:"
git log --oneline HEAD..upstream/main | head -20
echo "..."

# Create a sync branch for conflict resolution
SYNC_BRANCH="sync-$(date +%Y%m%d-%H%M%S)"
git checkout -b "$SYNC_BRANCH"

echo "=== Merging upstream/main (resolve conflicts, then commit) ==="
git merge upstream/main --no-commit --no-ff

echo ""
echo "Resolve conflicts, then:"
echo "  git add <resolved-files>"
echo "  git commit -m \"Merge upstream/main $(date +%Y-%m-%d)\""
echo "  git checkout main"
echo "  git merge $SYNC_BRANCH"
echo ""
echo "Or to abort: git merge --abort && git checkout main && git branch -D $SYNC_BRANCH"
