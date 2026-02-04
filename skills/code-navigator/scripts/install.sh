#!/bin/bash
# Code Navigator - Installation Script
# Usage: ./install.sh [--quiet]
#
# This script:
# 1. Installs the codenav Python package (idempotent)
# 2. Detects installed AI coding agents
# 3. Copies the skill to Claude Code if present (with backup)

set -e

QUIET=${1:-""}

log() {
    [ "$QUIET" != "--quiet" ] && echo "$1"
}

error() {
    echo "ERROR: $1" >&2
    exit 1
}

warn() {
    echo "WARNING: $1" >&2
}

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$SKILL_DIR/../.." && pwd)"

log ""
log "======================================"
log "  Code Navigator Installation"
log "======================================"
log ""

# 1. Install Python package (idempotent - check if already installed)
log "Checking codenav installation..."

install_codenav() {
    local pip_cmd="$1"

    # Check if already installed
    if python -c "import codenav" 2>/dev/null; then
        log "codenav already installed, upgrading..."
        $pip_cmd install --upgrade codenav 2>&1 || {
            # If PyPI upgrade fails, try local install
            if [ -f "$PROJECT_ROOT/pyproject.toml" ]; then
                log "PyPI upgrade failed, installing from local source..."
                $pip_cmd install --upgrade -e "$PROJECT_ROOT" 2>&1 || {
                    warn "Could not upgrade codenav"
                    return 1
                }
            fi
        }
    else
        log "Installing codenav Python package..."
        # Try PyPI first, fall back to local
        if ! $pip_cmd install codenav 2>&1; then
            if [ -f "$PROJECT_ROOT/pyproject.toml" ]; then
                log "PyPI install failed, installing from local source..."
                $pip_cmd install -e "$PROJECT_ROOT" 2>&1 || {
                    error "Failed to install codenav from: $PROJECT_ROOT"
                }
            else
                error "Failed to install codenav and no local source found"
            fi
        fi
    fi
}

if command -v pip &> /dev/null; then
    install_codenav "pip"
elif command -v pip3 &> /dev/null; then
    install_codenav "pip3"
else
    error "Python pip not found. Please install Python 3.8+ first."
fi

log "Python package installed."
log ""

# 2. Detect installed agents
log "Detecting AI coding agents..."
AGENTS_FOUND=()

[ -d "$HOME/.claude" ] && AGENTS_FOUND+=("claude-code")
[ -d "$HOME/.cursor" ] && AGENTS_FOUND+=("cursor")
[ -d "$HOME/.vscode" ] && AGENTS_FOUND+=("vscode")
[ -d "$HOME/.config/Code" ] && AGENTS_FOUND+=("vscode-linux")

if [ ${#AGENTS_FOUND[@]} -eq 0 ]; then
    log "No AI coding agents detected."
else
    log "Detected agents: ${AGENTS_FOUND[*]}"
fi
log ""

# 3. Copy skill to Claude Code if present (with backup)
if [ -d "$HOME/.claude" ]; then
    log "Installing skill to Claude Code..."
    CLAUDE_SKILL_DIR="$HOME/.claude/skills/code-navigator"

    # Backup existing skill if present
    if [ -d "$CLAUDE_SKILL_DIR" ]; then
        BACKUP_DIR="${CLAUDE_SKILL_DIR}.backup.$(date +%Y%m%d_%H%M%S)"
        log "Backing up existing skill to $BACKUP_DIR"
        cp -r "$CLAUDE_SKILL_DIR" "$BACKUP_DIR" || {
            warn "Could not create backup, continuing anyway..."
        }
    fi

    mkdir -p "$CLAUDE_SKILL_DIR"

    # Copy skill files (exclude scripts to avoid duplication)
    cp "$SKILL_DIR/SKILL.md" "$CLAUDE_SKILL_DIR/" || {
        error "Failed to copy SKILL.md"
    }

    if [ -d "$SKILL_DIR/references" ]; then
        cp -r "$SKILL_DIR/references" "$CLAUDE_SKILL_DIR/" || {
            warn "Could not copy references directory"
        }
    fi

    if [ -d "$SKILL_DIR/assets" ]; then
        cp -r "$SKILL_DIR/assets" "$CLAUDE_SKILL_DIR/" || {
            warn "Could not copy assets directory"
        }
    fi

    log "Skill installed to ~/.claude/skills/code-navigator"
fi

# 4. Show next steps
log ""
log "======================================"
log "  Installation Complete!"
log "======================================"
log ""
log "Next steps:"
log ""
log "1. Verify installation:"
log "   codenav --version"
log ""
log "2. Generate a code map in your project:"
log "   cd /your/project"
log "   codenav map ."
log ""
log "3. (Optional) Add MCP server to ~/.claude/settings.json:"
log '   "mcpServers": {'
log '     "codenav": {'
log '       "command": "python",'
log '       "args": ["-m", "codenav.mcp"]'
log '     }'
log '   }'
log ""
log "Documentation: https://github.com/efrenbl/code-navigator"
log ""
