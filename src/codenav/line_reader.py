#!/usr/bin/env python3
"""Line Reader - Read specific lines or ranges from files.

This module provides surgical precision for reading code - load only the exact
lines you need instead of entire files, dramatically reducing token usage.

Example:
    Command line usage:
        $ code-read src/api.py 45-60
        $ code-read src/api.py "10-20,45-60" -c 3
        $ code-read src/api.py --search "def process"

    Python API usage:
        >>> reader = LineReader('/path/to/project')
        >>> result = reader.read_lines('src/api.py', 45, 60)
        >>> for line in result['lines']:
        ...     print(f"{line['num']}: {line['content']}")
"""

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .colors import get_colors

__version__ = "1.2.0"


class LineReader:
    """Read specific lines from files efficiently.

    Provides methods to read single ranges, multiple ranges, and search
    for patterns within files, all with minimal overhead.

    Attributes:
        root_path: Base path for resolving relative file paths.

    Example:
        >>> reader = LineReader('/my/project')
        >>> result = reader.read_lines('src/api.py', 45, 60, context=2)
        >>> print(f"Read lines {result['actual'][0]}-{result['actual'][1]}")

        >>> # Read a function with smart truncation
        >>> symbol = reader.read_symbol('src/api.py', 45, 150, max_lines=50)
        >>> print(f"Truncated: {symbol['truncated']}")
    """

    def __init__(self, root_path: Optional[str] = None):
        """Initialize the line reader.

        Args:
            root_path: Base directory for resolving relative paths.
                      Defaults to current working directory.
        """
        self.root_path = Path(root_path) if root_path else Path.cwd()

    def _resolve_path(self, file_path: str) -> Path:
        """Resolve a file path relative to root with security validation.

        Args:
            file_path: Relative or absolute file path.

        Returns:
            Resolved absolute Path object.

        Raises:
            ValueError: If the resolved path escapes the root directory
                       (path traversal attempt).
        """
        path = Path(file_path)
        if not path.is_absolute():
            path = self.root_path / path

        resolved = path.resolve()
        root_resolved = self.root_path.resolve()

        # Security check: ensure path doesn't escape root directory
        try:
            resolved.relative_to(root_resolved)
        except ValueError:
            raise ValueError(
                f"Security error: path '{file_path}' escapes root directory. "
                f"Resolved to '{resolved}' which is outside '{root_resolved}'"
            ) from None

        return resolved

    def read_lines(
        self, file_path: str, start: int, end: Optional[int] = None, context: int = 0
    ) -> Dict:
        """Read specific lines from a file.

        Args:
            file_path: Path to the file to read.
            start: Starting line number (1-indexed).
            end: Ending line number (inclusive). Defaults to start.
            context: Number of context lines before and after.

        Returns:
            Dict with:
                - file: The file path
                - requested: [start, end] as requested
                - actual: [start, end] after applying context
                - total_lines: Total lines in file
                - lines: List of {num, content, in_range} dicts

        Example:
            >>> result = reader.read_lines('api.py', 45, 60, context=2)
            >>> print(result['lines'][0]['content'])
        """
        try:
            path = self._resolve_path(file_path)
        except ValueError as e:
            return {"error": str(e)}

        if not path.exists():
            return {"error": f"File not found: {file_path}"}

        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
        except Exception as e:
            return {"error": f"Failed to read file: {e}"}

        total_lines = len(all_lines)
        end = end or start

        actual_start = max(1, start - context)
        actual_end = min(total_lines, end + context)

        extracted = all_lines[actual_start - 1 : actual_end]

        lines_with_numbers = []
        for i, line in enumerate(extracted, start=actual_start):
            lines_with_numbers.append(
                {"num": i, "content": line.rstrip("\n\r"), "in_range": start <= i <= end}
            )

        return {
            "file": file_path,
            "requested": [start, end],
            "actual": [actual_start, actual_end],
            "total_lines": total_lines,
            "lines": lines_with_numbers,
        }

    def read_ranges(
        self, file_path: str, ranges: List[Tuple[int, int]], context: int = 0, collapse_gap: int = 5
    ) -> Dict:
        """Read multiple line ranges from a file efficiently.

        Intelligently merges overlapping or close ranges to minimize
        redundant reads while preserving the requested range markers.

        Args:
            file_path: Path to the file to read.
            ranges: List of (start, end) tuples (1-indexed).
            context: Context lines for each range.
            collapse_gap: Merge ranges if gap is smaller than this.

        Returns:
            Dict with:
                - file: The file path
                - total_lines: Total lines in file
                - sections: List of merged sections with lines

        Example:
            >>> ranges = [(10, 20), (25, 35), (100, 110)]
            >>> result = reader.read_ranges('api.py', ranges, context=2)
            >>> print(f"Got {len(result['sections'])} sections")
        """
        try:
            path = self._resolve_path(file_path)
        except ValueError as e:
            return {"error": str(e)}

        if not path.exists():
            return {"error": f"File not found: {file_path}"}

        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
        except Exception as e:
            return {"error": f"Failed to read file: {e}"}

        total_lines = len(all_lines)

        # Normalize and sort ranges
        normalized = []
        for start, end in ranges:
            s = max(1, start - context)
            e = min(total_lines, end + context)
            normalized.append((s, e, start, end))

        normalized.sort(key=lambda x: x[0])

        # Merge overlapping or close ranges
        merged = []
        for s, e, os, oe in normalized:
            if merged and s <= merged[-1][1] + collapse_gap:
                prev = merged[-1]
                merged[-1] = (prev[0], max(prev[1], e), prev[2])
                merged[-1][2].append((os, oe))
            else:
                merged.append((s, e, [(os, oe)]))

        # Extract lines for each merged range
        sections = []
        for actual_start, actual_end, original_ranges in merged:
            lines_with_numbers = []
            for i in range(actual_start - 1, actual_end):
                if i < len(all_lines):
                    line_num = i + 1
                    in_range = any(os <= line_num <= oe for os, oe in original_ranges)
                    lines_with_numbers.append(
                        {
                            "num": line_num,
                            "content": all_lines[i].rstrip("\n\r"),
                            "in_range": in_range,
                        }
                    )

            sections.append(
                {
                    "range": [actual_start, actual_end],
                    "original_ranges": original_ranges,
                    "lines": lines_with_numbers,
                }
            )

        return {"file": file_path, "total_lines": total_lines, "sections": sections}

    def read_symbol(
        self,
        file_path: str,
        start: int,
        end: int,
        include_context: bool = True,
        max_lines: int = 100,
    ) -> Dict:
        """Read a symbol (function, class, etc.) with smart truncation.

        For large symbols, shows signature + beginning + ... + end.
        This prevents large functions from consuming excessive tokens.

        Args:
            file_path: Path to the file.
            start: Symbol start line (1-indexed).
            end: Symbol end line (1-indexed).
            include_context: Add 2 lines before and 1 after.
            max_lines: Maximum lines before truncation kicks in.

        Returns:
            Dict with:
                - file: The file path
                - range: [start, end]
                - truncated: Boolean indicating if truncation occurred
                - skipped_lines: Number of lines omitted (if truncated)
                - lines: List of line dicts

        Example:
            >>> # A 200-line function will be truncated
            >>> result = reader.read_symbol('api.py', 100, 300, max_lines=50)
            >>> print(result['truncated'])  # True
            >>> print(result['skipped_lines'])  # ~150
        """
        try:
            path = self._resolve_path(file_path)
        except ValueError as e:
            return {"error": str(e)}

        if not path.exists():
            return {"error": f"File not found: {file_path}"}

        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
        except Exception as e:
            return {"error": f"Failed to read file: {e}"}

        total_lines = len(all_lines)
        start = max(1, start)
        end = min(total_lines, end)
        symbol_length = end - start + 1

        context_start = max(1, start - 2) if include_context else start
        context_end = min(total_lines, end + 1) if include_context else end

        if symbol_length <= max_lines:
            # Return full symbol
            lines = []
            for i in range(context_start - 1, context_end):
                if i < len(all_lines):
                    lines.append(
                        {
                            "num": i + 1,
                            "content": all_lines[i].rstrip("\n\r"),
                            "in_range": start <= (i + 1) <= end,
                        }
                    )

            return {"file": file_path, "range": [start, end], "truncated": False, "lines": lines}
        else:
            # Truncate: show beginning and end
            head_lines = max_lines // 2
            tail_lines = max_lines - head_lines - 1

            lines = []

            # Context before
            for i in range(context_start - 1, start - 1):
                if i < len(all_lines):
                    lines.append(
                        {"num": i + 1, "content": all_lines[i].rstrip("\n\r"), "in_range": False}
                    )

            # Head of symbol
            for i in range(start - 1, start - 1 + head_lines):
                if i < len(all_lines):
                    lines.append(
                        {"num": i + 1, "content": all_lines[i].rstrip("\n\r"), "in_range": True}
                    )

            # Ellipsis marker
            skipped = symbol_length - head_lines - tail_lines
            lines.append(
                {"num": None, "content": f"... ({skipped} lines omitted) ...", "in_range": True}
            )

            # Tail of symbol
            for i in range(end - tail_lines, end):
                if i < len(all_lines) and i >= 0:
                    lines.append(
                        {"num": i + 1, "content": all_lines[i].rstrip("\n\r"), "in_range": True}
                    )

            # Context after
            for i in range(end, context_end):
                if i < len(all_lines):
                    lines.append(
                        {"num": i + 1, "content": all_lines[i].rstrip("\n\r"), "in_range": False}
                    )

            return {
                "file": file_path,
                "range": [start, end],
                "truncated": True,
                "skipped_lines": skipped,
                "lines": lines,
            }

    def search_in_file(
        self, file_path: str, pattern: str, context: int = 2, max_matches: int = 10
    ) -> Dict:
        """Search for a pattern in a file and return matching lines with context.

        Args:
            file_path: Path to the file.
            pattern: Regex pattern or literal string to search.
            context: Context lines around each match.
            max_matches: Maximum matches to return.

        Returns:
            Dict with:
                - file: The file path
                - pattern: The search pattern
                - matches: Number of matches found
                - sections: List of matching sections with context

        Example:
            >>> result = reader.search_in_file('api.py', 'def process')
            >>> print(f"Found {result['matches']} matches")
        """
        try:
            path = self._resolve_path(file_path)
        except ValueError as e:
            return {"error": str(e)}

        if not path.exists():
            return {"error": f"File not found: {file_path}"}

        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
        except Exception as e:
            return {"error": f"Failed to read file: {e}"}

        # Find matches
        matches = []
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            regex = re.compile(re.escape(pattern), re.IGNORECASE)

        for i, line in enumerate(all_lines):
            if regex.search(line):
                matches.append(i + 1)
                if len(matches) >= max_matches:
                    break

        if not matches:
            return {"file": file_path, "pattern": pattern, "matches": 0, "sections": []}

        # Convert matches to ranges with context
        ranges = [(m, m) for m in matches]
        result = self.read_ranges(file_path, ranges, context=context)
        result["pattern"] = pattern
        result["matches"] = len(matches)

        return result


def format_output(
    result: Dict, style: str = "json", compact: bool = False, no_color: bool = False
) -> str:
    """Format the output for display.

    Args:
        result: The result dict to format.
        style: Output style ('json' or 'code').
        compact: If True, output compact JSON without indentation.
        no_color: If True, disable colored output.

    Returns:
        Formatted string representation.
    """
    if style == "json":
        if compact:
            return json.dumps(result, separators=(",", ":"))
        return json.dumps(result, indent=2)

    elif style == "code":
        c = get_colors(no_color=no_color)

        if "error" in result:
            return c.error(f"Error: {result['error']}")

        output = []
        output.append(c.cyan(f"# {result.get('file', 'Unknown file')}"))

        if "lines" in result:
            lines = result["lines"]
            for line in lines:
                num = line.get("num")
                content = line.get("content", "")
                if num is None:
                    # Ellipsis/omitted lines
                    output.append(c.dim(f"     {content}"))
                else:
                    in_range = line.get("in_range")
                    marker = c.green(">") if in_range else " "
                    line_num = c.cyan(f"{num:4d}")
                    if in_range:
                        output.append(f"{marker}{line_num} | {content}")
                    else:
                        # Context lines (dimmed)
                        output.append(f"{marker}{line_num} | {c.dim(content)}")

        elif "sections" in result:
            for i, section in enumerate(result["sections"]):
                if i > 0:
                    output.append(c.dim("..."))
                for line in section.get("lines", []):
                    num = line.get("num")
                    content = line.get("content", "")
                    if num is None:
                        output.append(c.dim(f"     {content}"))
                    else:
                        in_range = line.get("in_range")
                        marker = c.green(">") if in_range else " "
                        line_num = c.cyan(f"{num:4d}")
                        if in_range:
                            output.append(f"{marker}{line_num} | {content}")
                        else:
                            output.append(f"{marker}{line_num} | {c.dim(content)}")

        return "\n".join(output)

    return json.dumps(result)


def add_read_arguments(parser: argparse.ArgumentParser) -> None:
    """Add read command arguments to a parser.

    Args:
        parser: The argument parser to add arguments to.
    """
    parser.add_argument("file", help="Path to the file to read")
    parser.add_argument("lines", nargs="?", help='Line range (e.g., "10", "10-20", "10,20,30-40")')
    parser.add_argument("-r", "--root", help="Root directory for relative paths")
    parser.add_argument(
        "-c", "--context", type=int, default=0, help="Number of context lines (default: 0)"
    )
    parser.add_argument("-s", "--search", help="Search for pattern instead of line numbers")
    parser.add_argument(
        "--symbol", action="store_true", help="Read as symbol with smart truncation"
    )
    parser.add_argument(
        "--max-lines", type=int, default=100, help="Maximum lines before truncation (default: 100)"
    )
    parser.add_argument(
        "-o",
        "--output",
        choices=["json", "code"],
        default="json",
        help="Output format (default: json)",
    )
    parser.add_argument(
        "--compact", action="store_true", help="Output compact JSON (default: pretty-printed)"
    )
    parser.add_argument("--no-color", action="store_true", help="Disable colored output")


def run_read(args: argparse.Namespace) -> None:
    """Execute the read command with parsed arguments.

    Args:
        args: Parsed command-line arguments.
    """
    reader = LineReader(args.root)

    if args.search:
        result = reader.search_in_file(args.file, args.search, context=args.context)
    elif args.lines:
        # Parse line specification with validation
        ranges = []
        for part in args.lines.split(","):
            part = part.strip()
            if not part:
                # Skip empty parts (e.g., "10,,20" or trailing comma)
                continue
            try:
                if "-" in part:
                    start_str, end_str = part.split("-", 1)
                    start = int(start_str.strip())
                    end = int(end_str.strip())
                    if start < 1:
                        result = {
                            "error": f"Invalid line number: {start}. Line numbers must be >= 1"
                        }
                        print(
                            format_output(
                                result, args.output, compact=args.compact, no_color=args.no_color
                            )
                        )
                        return
                    if end < 1:
                        result = {"error": f"Invalid line number: {end}. Line numbers must be >= 1"}
                        print(
                            format_output(
                                result, args.output, compact=args.compact, no_color=args.no_color
                            )
                        )
                        return
                    if start > end:
                        result = {"error": f"Invalid range: {start}-{end}. Start must be <= end"}
                        print(
                            format_output(
                                result, args.output, compact=args.compact, no_color=args.no_color
                            )
                        )
                        return
                    ranges.append((start, end))
                else:
                    line = int(part)
                    if line < 1:
                        result = {
                            "error": f"Invalid line number: {line}. Line numbers must be >= 1"
                        }
                        print(
                            format_output(
                                result, args.output, compact=args.compact, no_color=args.no_color
                            )
                        )
                        return
                    ranges.append((line, line))
            except ValueError:
                result = {
                    "error": f"Invalid line specification: '{part}'. Expected number or range (e.g., '10' or '10-20')"
                }
                print(
                    format_output(result, args.output, compact=args.compact, no_color=args.no_color)
                )
                return

        if not ranges:
            result = {"error": "No valid line ranges specified"}
            print(format_output(result, args.output, compact=args.compact, no_color=args.no_color))
            return

        if len(ranges) == 1 and args.symbol:
            result = reader.read_symbol(
                args.file,
                ranges[0][0],
                ranges[0][1],
                include_context=args.context > 0,
                max_lines=args.max_lines,
            )
        elif len(ranges) == 1:
            result = reader.read_lines(args.file, ranges[0][0], ranges[0][1], context=args.context)
        else:
            result = reader.read_ranges(args.file, ranges, context=args.context)
    else:
        # Default: show file info
        try:
            path = reader._resolve_path(args.file)
        except ValueError as e:
            result = {"error": str(e)}
            print(format_output(result, args.output, compact=args.compact, no_color=args.no_color))
            return

        if path.exists():
            with open(path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            result = {
                "file": args.file,
                "total_lines": len(lines),
                "hint": 'Specify lines to read (e.g., "10-20") or use --search',
            }
        else:
            result = {"error": f"File not found: {args.file}"}

    print(format_output(result, args.output, compact=args.compact, no_color=args.no_color))


def main():
    """Command-line interface for the line reader.

    Usage:
        code-read FILE LINES [-c CONTEXT] [--symbol] [-o FORMAT]
        code-read FILE --search PATTERN

    Examples:
        $ code-read src/api.py 45-60 -c 2
        $ code-read src/api.py "10,20-30,50" --symbol
        $ code-read src/api.py --search "def process" -o code
    """
    parser = argparse.ArgumentParser(
        description="Read specific lines from files for token-efficient code viewing",
        epilog="Example: code-read src/api.py 45-60 -c 2 -o code",
    )
    add_read_arguments(parser)
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")

    args = parser.parse_args()
    run_read(args)


if __name__ == "__main__":
    main()
