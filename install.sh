#!/bin/sh
# Shipyard for Copilot: project install bootstrap.
#
#   sh install.sh init   [--target DIR] [--skip-github] [--skip GLOB] [--force] [--dry-run]
#   sh install.sh update [--target DIR] [--force] [--dry-run]
#   sh install.sh status [--target DIR]
#
# Fetches a shallow clone of shipyard-copilot into a temporary folder and runs shipyard/scripts/install.py from it.
# The target defaults to the current directory. To uninstall, run the copy the install left behind:
#
#   python3 shipyard/scripts/install.py remove
#
# SHIPYARD_COPILOT_REPO and SHIPYARD_COPILOT_REF override the repository URL and the branch or tag.
set -eu

REPO="${SHIPYARD_COPILOT_REPO:-https://github.com/vineethvarghese/shipyard-copilot.git}"
REF="${SHIPYARD_COPILOT_REF:-main}"

for tool in git python3; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "install.sh: $tool is required" >&2
    exit 1
  fi
done

case "${1:-}" in
  init|update|status) ;;
  remove) echo "install.sh: run 'python3 shipyard/scripts/install.py remove' inside the project instead" >&2; exit 1 ;;
  *) echo "usage: sh install.sh init|update|status [--target DIR] [options]" >&2; exit 1 ;;
esac

tmp="$(mktemp -d 2>/dev/null || mktemp -d -t shipyard)"
trap 'rm -rf "$tmp"' EXIT INT TERM

git clone --quiet --depth 1 --branch "$REF" "$REPO" "$tmp/src"
python3 "$tmp/src/shipyard/scripts/install.py" "$@" --source "$tmp/src"
