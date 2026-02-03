#!/usr/bin/env python3
"""Unified CLI for codenav.

This module provides a single entry point `codenav` with subcommands for all
codenav functionality:
    - codenav map: Generate a code map of a codebase
    - codenav search: Search for symbols in the code map
    - codenav read: Read specific lines from files
    - codenav stats: Show codebase statistics (shortcut for search --stats)
    - codenav completion: Generate shell completion scripts
    - codenav watch: Watch for changes and auto-update map
    - codenav export: Export code map to different formats

Example:
    $ codenav map /path/to/project -o .codenav.json
    $ codenav search "UserService" --type class
    $ codenav read src/api.py 45-60
    $ codenav stats
    $ codenav completion bash > ~/.bash_completion.d/codenav
    $ codenav watch /path/to/project
    $ codenav export -f markdown -o docs/codebase.md
"""

import argparse
import sys

from . import __version__
from .code_navigator import add_map_arguments, run_map
from .code_search import add_search_arguments, run_search
from .completions import run_completion
from .exporters import run_export
from .line_reader import add_read_arguments, run_read
from .watcher import run_watch


def main():
    """Unified command-line interface for codenav.

    Usage:
        codenav map PATH [-o OUTPUT] [-i IGNORE...] [--compact]
        codenav search QUERY [--type TYPE] [--file PATTERN] [--limit N]
        codenav read FILE LINES [-c CONTEXT] [--symbol]
        codenav stats [-m MAP] [--compact]
        codenav completion SHELL
        codenav watch PATH [-o OUTPUT] [--debounce N]
        codenav export -f FORMAT [-o OUTPUT]

    Example:
        $ codenav map /my/project -o .codenav.json
        $ codenav search "payment" --type function
        $ codenav read src/api.py 45-60 -c 2
        $ codenav stats
        $ codenav completion bash > ~/.bash_completion.d/codenav
        $ codenav watch /my/project
        $ codenav export -f markdown -o docs/codebase.md
    """
    parser = argparse.ArgumentParser(
        prog="codenav",
        description="Token-efficient code navigation - reduce token usage by 97%",
        epilog="Run 'codenav <command> --help' for more information on a command.",
    )
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    # codenav map
    map_parser = subparsers.add_parser(
        "map",
        help="Generate a code map of a codebase",
        description="Scan a codebase and generate a JSON index of all symbols.",
        epilog="Example: codenav map /my/project -o .codenav.json",
    )
    add_map_arguments(map_parser)

    # codenav search
    search_parser = subparsers.add_parser(
        "search",
        help="Search for symbols in the code map",
        description="Search through a code map for symbols, files, and dependencies.",
        epilog='Example: codenav search "payment" --type function',
    )
    add_search_arguments(search_parser)

    # codenav read
    read_parser = subparsers.add_parser(
        "read",
        help="Read specific lines from files",
        description="Read specific lines or ranges from files for token-efficient viewing.",
        epilog="Example: codenav read src/api.py 45-60 -c 2",
    )
    add_read_arguments(read_parser)

    # codenav stats (shortcut for search --stats)
    stats_parser = subparsers.add_parser(
        "stats",
        help="Show codebase statistics (shortcut for search --stats)",
        description="Display statistics about the indexed codebase.",
        epilog="Example: codenav stats -m .codenav.json",
    )
    stats_parser.add_argument(
        "-m",
        "--map",
        default=".codenav.json",
        help="Path to code map file (default: .codenav.json)",
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

    # codenav completion
    completion_parser = subparsers.add_parser(
        "completion",
        help="Generate shell completion script",
        description="Generate autocompletion script for bash or zsh.",
        epilog="Example: codenav completion bash > ~/.bash_completion.d/codenav",
    )
    completion_parser.add_argument(
        "shell",
        choices=["bash", "zsh"],
        help="Shell type (bash or zsh)",
    )

    # codenav watch
    watch_parser = subparsers.add_parser(
        "watch",
        help="Watch for changes and auto-update map",
        description="Monitor a codebase for changes and automatically update the code map.",
        epilog="Example: codenav watch /my/project -o .codenav.json",
    )
    watch_parser.add_argument("path", help="Path to the codebase root directory")
    watch_parser.add_argument(
        "-o", "--output", default=".codenav.json", help="Output file path (default: .codenav.json)"
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

    # codenav export
    export_parser = subparsers.add_parser(
        "export",
        help="Export code map to different formats",
        description="Export the code map to Markdown, HTML, or GraphViz format.",
        epilog="Example: codenav export -f markdown -o docs/codebase.md",
    )
    export_parser.add_argument(
        "-m",
        "--map",
        default=".codenav.json",
        help="Path to code map file (default: .codenav.json)",
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
