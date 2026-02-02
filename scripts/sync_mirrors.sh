#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${SOURCEGRAPH_DATA_DIR:-$ROOT_DIR/sourcegraph-data}"
OWNER="${SOURCEGRAPH_REPO_OWNER:-clarisights}"
UPSTREAM_BASE="${SOURCEGRAPH_UPSTREAM_BASE:-git@github.com:$OWNER}"

REPOS=(
  "adwyze"
  "adwyze-frontend"
)

mirror_repo() {
  local name="$1"
  local target_dir="$DATA_DIR/repos/github.com/$OWNER/${name}.git"
  mkdir -p "$(dirname "$target_dir")"

  if [[ -d "$target_dir" ]]; then
    echo "Updating mirror for $name..."
    git --git-dir="$target_dir" fetch --all --prune
  else
    echo "Creating mirror for $name..."
    git clone --mirror "${UPSTREAM_BASE}/${name}.git" "$target_dir"
  fi

  touch "$target_dir/git-daemon-export-ok"
}

main() {
  if ! command -v git >/dev/null 2>&1; then
    echo "git is required to mirror repositories" >&2
    exit 1
  fi

  for repo in "${REPOS[@]}"; do
    mirror_repo "$repo"
  done

  echo "Mirrors synchronized under $DATA_DIR/repos/github.com/$OWNER"
}

main "$@"
