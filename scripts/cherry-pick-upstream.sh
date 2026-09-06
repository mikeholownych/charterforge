#!/usr/bin/env bash
# Cherry-pick specific upstream fixes by commit hash
# Usage: ./scripts/cherry-pick-upstream.sh <commit-hash> [<commit-hash>...]

set -euo pipefail

if [ $# -eq 0 ]; then
    echo "Usage: $0 <commit-hash> [<commit-hash>...]"
    echo ""
    echo "High-value fix batches:"
    echo ""
    echo "Agent streaming & responses:"
    echo "  7b72fd1247 390c27c6db 562ee8ab76 3755dca7d6 c3e9defd18"
    echo ""
    echo "Session/state management:"
    echo "  86b204081d ab281990b8 73f68362b3 61635e1b53 bcc2e65818 e9160625dc"
    echo ""
    echo "Performance (shared infra):"
    echo "  c3b411dfb7 561b053f79 c96568f66c 2b55ded1ac"
    echo ""
    echo "Model/provider updates:"
    echo "  7e60d0c042 7f2aa70add d6bb94a1fb b462989a68 c2954c8934 0ee98eda52 4359af7705"
    echo ""
    echo "Gateway/multiplexing:"
    echo "  17f86ab36f eed481bd34 a6351a71e5 74b00d7a97 2ce6f5c538 ca42d7a034"
    exit 1
fi

git fetch upstream

for commit in "$@"; do
    echo "=== Cherry-picking $commit ==="
    git cherry-pick "$commit" || {
        echo "Conflict! Resolve then: git cherry-pick --continue"
        echo "Or abort: git cherry-pick --abort"
        exit 1
    }
done

echo "All cherry-picks applied successfully"
