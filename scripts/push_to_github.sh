#!/usr/bin/env bash
# Usage: scripts/push_to_github.sh [repo-name]   (default: campus-support-datagen)
# Prerequisite: create an EMPTY public repo https://github.com/yugundhar-gurjalwar/<repo-name> in the GitHub UI
# (no README/license), and be authenticated (gh auth login, a credential helper, or an SSH key).
set -euo pipefail
REPO="${1:-campus-support-datagen}"
OWNER="yugundhar-gurjalwar"
git remote remove origin 2>/dev/null || true
git remote add origin "https://github.com/${OWNER}/${REPO}.git"
git branch -M main
git push -u origin main
echo "Pushed: https://github.com/${OWNER}/${REPO}"
