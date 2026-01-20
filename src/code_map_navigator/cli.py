#!/usr/bin/env python3
"""Unified CLI for code-map-navigator.

This module provides a single entry point `codemap` with subcommands for all
code-map-navigator functionality:
    - codemap map: Generate a code map of a codebase
    - codemap search: Search for symbols in the code map
    - codemap read: Read specific lines from files
    - codemap stats: Show codebase statistics (shortcut for search --stats)
    - codemap completion: Generate shell completion scripts
    - codemap watch: Watch for changes and auto-update map
    - codemap export: Export code map to different formats

Example:
    $ codemap map /path/to/project -o .codemap.json
    $ codemap search "UserService" --type class
    $ codemap read src/api.py 45-60
    $ codemap stats
    $ codemap completion bash > ~/.bash_completion.d/codemap
    $ codemap watch /path/to/project
    $ codemap export -f markdown -o docs/codebase.md
"""

import argparse
import sys

from . import __version__
from .code_mapper import add_map_arguments, run_map
from .code_search import add_search_arguments, run_search
from .completions import run_completion
from .exporters import run_export
from .line_reader import add_read_arguments, run_read
from .watcher import run_watch


def main():
    """Unified command-line interface for code-map-navigator.

    Usage:
        codemap map PATH [-o OUTPUT] [-i IGNORE...] [--compact]
        codemap search QUERY [--type TYPE] [--file PATTERN] [--limit N]
        codemap read FILE LINES [-c CONTEXT] [--symbol]
        codemap stats [-m MAP] [--compact]
        codemap completion SHELL
        codemap watch PATH [-o OUTPUT] [--debounce N]
        codemap export -f FORMAT [-o OUTPUT]

    Example:
        $ codemap map /my/project -o .codemap.json
        $ codemap search "payment" --type function
        $ codemap read src/api.py 45-60 -c 2
        $ codemap stats
        $ codemap completion bash > ~/.bash_completion.d/codemap
        $ codemap watch /my/project
        $ codemap export -f markdown -o docs/codebase.md
    """
    parser = argparse.ArgumentParser(
        prog="codemap",
        description="Token-efficient code navigation - reduce token usage by 97%",
        epilog="Run 'codemap <command> --help' for more information on a command.",
    )
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    # codemap map
    map_parser = subparsers.add_parser(
        "map",
        help="Generate a code map of a codebase",
        description="Scan a codebase and generate a JSON index of all symbols.",
        epilog="Example: codemap map /my/project -o .codemap.json",
    )
    add_map_arguments(map_parser)

    # codemap search
    search_parser = subparsers.add_parser(
        "search",
        help="Search for symbols in the code map",
        description="Search through a code map for symbols, files, and dependencies.",
        epilog='Example: codemap search "payment" --type function',
    )
    add_search_arguments(search_parser)

    # codemap read
    read_parser = subparsers.add_parser(
        "read",
        help="Read specific lines from files",
        description="Read specific lines or ranges from files for token-efficient viewing.",
        epilog="Example: codemap read src/api.py 45-60 -c 2",
    )
    add_read_arguments(read_parser)

    # codemap stats (shortcut for search --stats)
    stats_parser = subparsers.add_parser(
        "stats",
        help="Show codebase statistics (shortcut for search --stats)",
        description="Display statistics about the indexed codebase.",
        epilog="Example: codemap stats -m .codemap.json",
    )
    stats_parser.add_argument(
        "-m",
        "--map",
        default=".codemap.json",
        help="Path to code map file (default: .codemap.json)",
    )
    stats_parser.add_argument(
        "--compact", action="store_true", help="Output compact JSON (default: pretty-printed)"
    )
    stats_parser.add_argument(
        "-o",
        "--output",
        choices=["json", "table"],
        default="json",
        help="Output format (default: json)",
    )
    stats_parser.add_argument("--no-color", action="store_true", help="Disable colored output")

    # codemap completion
    completion_parser = subparsers.add_parser(
        "completion",
        help="Generate shell completion script",
        description="Generate autocompletion script for bash or zsh.",
        epilog="Example: codemap completion bash > ~/.bash_completion.d/codemap",
    )
    completion_parser.add_argument(
        "shell",
        choices=["bash", "zsh"],
        help="Shell type (bash or zsh)",
    )

    # codemap watch
    watch_parser = subparsers.add_parser(
        "watch",
        help="Watch for changes and auto-update map",
        description="Monitor a codebase for changes and automatically update the code map.",
        epilog="Example: codemap watch /my/project -o .codemap.json",
    )
    watch_parser.add_argument("path", help="Path to the codebase root directory")
    watch_parser.add_argument(
        "-o", "--output", default=".codemap.json", help="Output file path (default: .codemap.json)"
    )
    watch_parser.add_argument("-i", "--ignore", nargs="*", help="Additional patterns to ignore")
    watch_parser.add_argument(
        "--git-only", action="store_true", help="Only scan files tracked by git"
    )
    watch_parser.add_argument(
        "--use-gitignore", action="store_true", help="Also ignore patterns from .gitignore"
    )
    watch_parser.add_argument(
        "--compact", action="store_true", help="Output compact JSON (default: pretty-printed)"
    )
    watch_parser.add_argument("--no-color", action="store_true", help="Disable colored output")
    watch_parser.add_argument(
        "--debounce",
        type=float,
        default=1.0,
        help="Seconds to wait after change before updating (default: 1.0)",
    )

    # codemap export
    export_parser = subparsers.add_parser(
        "export",
        help="Export code map to different formats",
        description="Export the code map to Markdown, HTML, or GraphViz format.",
        epilog="Example: codemap export -f markdown -o docs/codebase.md",
    )
    export_parser.add_argument(
        "-m",
        "--map",
        default=".codemap.json",
        help="Path to code map file (default: .codemap.json)",
    )
    export_parser.add_argument(
        "-f",
        "--format",
        choices=["markdown", "md", "html", "graphviz", "dot"],
        default="markdown",
        help="Export format (default: markdown)",
    )
    export_parser.add_argument("-o", "--output", help="Output file (default: stdout)")
    export_parser.add_argument("--no-color", action="store_true", help="Disable colored output")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "map":
        run_map(args)
    elif args.command == "search":
        run_search(args)
    elif args.command == "read":
        run_read(args)
    elif args.command == "stats":
        # Convert stats args to search args format
        args.stats = True
        args.query = None
        args.type = None
        args.file = None
        args.files = False
        args.structure = None
        args.deps = None
        args.limit = 10
        args.no_fuzzy = False
        args.check_stale = False
        args.warn_stale = False
        args.since_commit = None
        run_search(args)
    elif args.command == "completion":
        run_completion(args.shell)
    elif args.command == "watch":
        run_watch(args)
    elif args.command == "export":
        run_export(args)


if __name__ == "__main__":
    main()
