#!/usr/bin/env python3
"""Watch mode for automatic code map updates.

Monitors a codebase for file changes and automatically updates the code map
when changes are detected. Uses polling (no external dependencies).

Example:
    Command line usage:
        $ codenav watch /path/to/project -o .codenav.json

    Python API usage:
        >>> watcher = CodenavWatcher('/path/to/project', '.codenav.json')
        >>> watcher.start()  # Blocks until Ctrl+C
"""

import json
import os
import shutil
import signal
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

from .code_navigator import DEFAULT_IGNORE_PATTERNS, LANGUAGE_EXTENSIONS, CodeNavigator
from .colors import get_colors

__version__ = "1.4.1"


class CodenavWatcher:
    """Watches a codebase for changes and updates the code map automatically.

    Attributes:
        root_path: Path to the codebase root.
        output_path: Path to the output .codenav.json file.
        ignore_patterns: Patterns to ignore.
        debounce: Seconds to wait after change before updating.
        git_only: Only watch git-tracked files.
        use_gitignore: Use .gitignore patterns.

    Example:
        >>> watcher = CodenavWatcher('/my/project', '.codenav.json')
        >>> watcher.start()
    """

    def __init__(
        self,
        root_path: str,
        output_path: str = ".codenav.json",
        ignore_patterns: List[str] = None,
        debounce: float = 1.0,
        git_only: bool = False,
        use_gitignore: bool = False,
        poll_interval: float = 1.0,
        compact: bool = False,
        no_color: bool = False,
    ):
        """Initialize the watcher.

        Args:
            root_path: Path to the codebase root.
            output_path: Path to output file (default: .codenav.json).
            ignore_patterns: Additional patterns to ignore.
            debounce: Seconds to wait after change before updating (default: 1.0).
            git_only: Only watch git-tracked files.
            use_gitignore: Use .gitignore patterns.
            poll_interval: Seconds between polls (default: 1.0).
            compact: Output compact JSON.
            no_color: Disable colored output.
        """
        self.root_path = Path(root_path).resolve()
        self.output_path = output_path
        if not os.path.isabs(self.output_path):
            self.output_path = str(self.root_path / self.output_path)

        self.ignore_patterns = list(ignore_patterns or DEFAULT_IGNORE_PATTERNS)
        self.debounce = debounce
        self.git_only = git_only
        self.use_gitignore = use_gitignore
        self.poll_interval = poll_interval
        self.compact = compact
        self.no_color = no_color

        self._running = False
        self._file_hashes: Dict[str, str] = {}
        self._last_change_time: float = 0
        self._pending_update = False
        self._colors = get_colors(no_color=no_color)

    def _get_watched_files(self) -> Set[Path]:
        """Get all files that should be watched.

        Returns:
            Set of file paths to watch.
        """
        files = set()

        for root, dirs, filenames in os.walk(self.root_path):
            # Filter directories
            dirs[:] = [d for d in dirs if not self._should_ignore(Path(root) / d)]

            for filename in filenames:
                file_path = Path(root) / filename
                if self._should_ignore(file_path):
                    continue

                # Check if it's a supported language file
                ext = file_path.suffix.lower()
                is_supported = any(ext in exts for exts in LANGUAGE_EXTENSIONS.values())
                if is_supported:
                    files.add(file_path)

        return files

    def _should_ignore(self, path: Path) -> bool:
        """Check if a path should be ignored.

        Args:
            path: Path to check.

        Returns:
            True if the path should be ignored.
        """
        import fnmatch

        path_str = str(path)
        name = path.name

        for pattern in self.ignore_patterns:
            if fnmatch.fnmatch(name, pattern):
                return True
            if pattern in path_str:
                return True

        return False

    def _hash_file(self, file_path: Path) -> Optional[str]:
        """Calculate hash of a file's content.

        Args:
            file_path: Path to the file.

        Returns:
            Hash string, or None if file cannot be read (deleted, permission denied, etc).
        """
        try:
            # Check if file exists and is a regular file (not symlink pointing elsewhere)
            if not file_path.is_file():
                return None
            from . import compute_content_hash

            content = file_path.read_text(encoding="utf-8", errors="replace")
            return compute_content_hash(content)
        except OSError:
            # File may have been deleted, or permission denied - this is expected
            # during rapid file changes (TOCTOU race condition handling)
            return None

    def _check_for_changes(self) -> bool:
        """Check if any watched files have changed.

        Handles TOCTOU (time-of-check to time-of-use) race conditions by:
        - Tracking files that become unreadable (deleted during scan)
        - Using explicit markers for inaccessible files
        - Gracefully handling files that disappear between listing and hashing

        Returns:
            True if changes were detected.
        """
        current_files = self._get_watched_files()
        current_hashes: Dict[str, str] = {}

        for file_path in current_files:
            try:
                rel_path = str(file_path.relative_to(self.root_path))
            except ValueError:
                # File somehow escaped root (shouldn't happen, but be safe)
                continue

            file_hash = self._hash_file(file_path)
            if file_hash is not None:
                current_hashes[rel_path] = file_hash
            else:
                # File existed in listing but couldn't be read (TOCTOU race)
                # Mark as inaccessible so we detect when it becomes readable again
                current_hashes[rel_path] = "__INACCESSIBLE__"

        # Check for changes
        changed = False

        # New or modified files
        for rel_path, file_hash in current_hashes.items():
            if rel_path not in self._file_hashes:
                changed = True
                break
            if self._file_hashes[rel_path] != file_hash:
                changed = True
                break

        # Deleted files
        if not changed:
            for rel_path in self._file_hashes:
                if rel_path not in current_hashes:
                    changed = True
                    break

        # Update stored hashes
        self._file_hashes = current_hashes
        return changed

    def _update_map(self) -> None:
        """Update the code map."""
        c = self._colors

        print(f"\n{c.cyan('Updating code map...')}", file=sys.stderr)
        start_time = time.time()

        try:
            mapper = CodeNavigator(
                str(self.root_path),
                self.ignore_patterns,
                git_only=self.git_only,
                use_gitignore=self.use_gitignore,
            )

            # Use incremental scan if map exists
            if os.path.exists(self.output_path):
                code_map = mapper.scan_incremental(self.output_path)
            else:
                code_map = mapper.scan()

            # Write the map atomically (write to temp file, then rename)
            # This prevents corruption if disk is full or process is interrupted
            output_dir = os.path.dirname(self.output_path) or "."
            tmp_fd = None
            tmp_path = None
            try:
                tmp_fd, tmp_path = tempfile.mkstemp(
                    suffix=".json.tmp", dir=output_dir, prefix=".codenav_"
                )
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                    tmp_fd = None  # os.fdopen takes ownership
                    if self.compact:
                        json.dump(code_map, f, separators=(",", ":"))
                    else:
                        json.dump(code_map, f, indent=2)

                # Atomic rename (on same filesystem)
                shutil.move(tmp_path, self.output_path)
                tmp_path = None  # Successfully moved
            finally:
                # Clean up temp file if write or move failed
                if tmp_fd is not None:
                    os.close(tmp_fd)
                if tmp_path is not None and os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass

            elapsed = time.time() - start_time
            stats = code_map["stats"]

            if "files_unchanged" in stats:
                print(
                    f"{c.success('✓')} Updated in {elapsed:.2f}s: "
                    f"{c.dim(str(stats.get('files_unchanged', 0)))} unchanged, "
                    f"{c.yellow(str(stats.get('files_modified', 0)))} modified, "
                    f"{c.green(str(stats.get('files_added', 0)))} added, "
                    f"{c.magenta(str(stats.get('files_deleted', 0)))} deleted",
                    file=sys.stderr,
                )
            else:
                print(
                    f"{c.success('✓')} Generated in {elapsed:.2f}s: "
                    f"{c.green(str(stats['files_processed']))} files, "
                    f"{c.green(str(stats['symbols_found']))} symbols",
                    file=sys.stderr,
                )

        except OSError as e:
            print(f"{c.error('✗')} Disk error updating map: {e}", file=sys.stderr)
        except (json.JSONDecodeError, TypeError) as e:
            print(f"{c.error('✗')} Data error in map: {e}", file=sys.stderr)
        except Exception as e:
            print(
                f"{c.error('✗')} Unexpected error updating map: {type(e).__name__}: {e}",
                file=sys.stderr,
            )

    def _initial_scan(self) -> None:
        """Perform initial scan to populate file hashes."""
        c = self._colors
        print(f"{c.cyan('Performing initial scan...')}", file=sys.stderr)

        # Get initial file hashes
        for file_path in self._get_watched_files():
            rel_path = str(file_path.relative_to(self.root_path))
            file_hash = self._hash_file(file_path)
            if file_hash:
                self._file_hashes[rel_path] = file_hash

        # Generate initial map if it doesn't exist
        if not os.path.exists(self.output_path):
            self._update_map()

        print(
            f"{c.success('✓')} Watching {c.green(str(len(self._file_hashes)))} files",
            file=sys.stderr,
        )
        print(f"{c.dim('Press Ctrl+C to stop')}", file=sys.stderr)

    def start(self) -> None:
        """Start watching for changes. Blocks until interrupted.

        Use Ctrl+C to stop watching.
        """
        c = self._colors
        self._running = True

        # Handle Ctrl+C gracefully
        def signal_handler(signum, frame):
            self._running = False
            print(f"\n{c.dim('Stopping watcher...')}", file=sys.stderr)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        print(f"{c.bold('Code Map Watcher')}", file=sys.stderr)
        print(f"  Root: {c.cyan(str(self.root_path))}", file=sys.stderr)
        print(f"  Output: {c.cyan(self.output_path)}", file=sys.stderr)

        self._initial_scan()

        while self._running:
            try:
                if self._check_for_changes():
                    self._last_change_time = time.time()
                    self._pending_update = True

                # Debounce: wait for debounce period after last change
                if self._pending_update:
                    if time.time() - self._last_change_time >= self.debounce:
                        self._update_map()
                        self._pending_update = False

                time.sleep(self.poll_interval)

            except Exception as e:
                print(f"{c.error('Error')}: {e}", file=sys.stderr)
                time.sleep(self.poll_interval)

        print(f"{c.success('✓')} Watcher stopped", file=sys.stderr)

    def stop(self) -> None:
        """Stop watching."""
        self._running = False


def run_watch(args) -> None:
    """Run the watch command.

    Args:
        args: Parsed command-line arguments.
    """
    ignore_patterns = DEFAULT_IGNORE_PATTERNS.copy()
    if getattr(args, "ignore", None):
        ignore_patterns.extend(args.ignore)

    watcher = CodenavWatcher(
        root_path=args.path,
        output_path=getattr(args, "output", ".codenav.json"),
        ignore_patterns=ignore_patterns,
        debounce=getattr(args, "debounce", 1.0),
        git_only=getattr(args, "git_only", False),
        use_gitignore=getattr(args, "use_gitignore", False),
        compact=getattr(args, "compact", False),
        no_color=getattr(args, "no_color", False),
    )

    watcher.start()
