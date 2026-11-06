#!/usr/bin/env bash
# Install the TAL Builder skill and its slash commands.
#   ./install.sh                 into ~/.claude (every project)
#   ./install.sh path/to/project into that project's .claude/
# Existing files with the same names are replaced; nothing else is touched.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
if [ $# -eq 0 ]; then dest="$HOME/.claude"; else mkdir -p "$1"; dest="$(cd "$1" && pwd)/.claude"; fi
mkdir -p "$dest/skills" "$dest/commands"
rm -rf "$dest/skills/tal-builder"
cp -R "$here/.claude/skills/tal-builder" "$dest/skills/tal-builder"
find "$dest/skills/tal-builder" -name __pycache__ -type d -prune -exec rm -rf {} +
cp "$here"/.claude/commands/tal-*.md "$dest/commands/"
echo "Installed the tal-builder skill and $(ls "$here"/.claude/commands/tal-*.md | wc -l | tr -d ' ') commands into $dest"
echo "Next: in your project, put PROSPEO_API_KEY in .env (see .env.example), then run /tal-init in Claude Code."
