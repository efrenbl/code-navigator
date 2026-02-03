#!/usr/bin/env python3
"""Terminal color utilities for Claude Code Navigator.

Provides ANSI color support with automatic detection of terminal capabilities.
Respects the NO_COLOR environment variable (https://no-color.org/).

Example:
    >>> from codenav.colors import Colors
    >>> c = Colors()
    >>> print(c.green("Success!"))
    >>> print(c.cyan("Line 42"))
"""

import os
import sys
import threading

__version__ = "1.2.0"


class Colors:
    """ANSI color utility class with automatic terminal detection.

    Attributes:
        enabled: Whether colors are enabled (auto-detected or manually set).

    Example:
        >>> c = Colors()
        >>> print(c.green("found") + " in " + c.cyan("file.py"))
    """

    # ANSI escape codes
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Foreground colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright foreground colors
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    def __init__(self, enabled: bool = None):
        """Initialize Colors with optional override.

        Args:
            enabled: Force colors on/off. If None, auto-detect.
        """
        if enabled is not None:
            self.enabled = enabled
        else:
            self.enabled = self._should_enable_colors()

    def _should_enable_colors(self) -> bool:
        """Determine if colors should be enabled based on environment."""
        # Respect NO_COLOR environment variable (https://no-color.org/)
        if os.environ.get("NO_COLOR"):
            return False

        # Check FORCE_COLOR for explicit enable
        if os.environ.get("FORCE_COLOR"):
            return True

        # Check if stdout is a TTY
        if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
            return False

        # Check TERM environment variable
        term = os.environ.get("TERM", "")
        if term == "dumb":
            return False

        # Windows: check for Windows Terminal or newer cmd
        if sys.platform == "win32":
            # Windows Terminal and modern Windows 10+ support ANSI
            return (
                os.environ.get("WT_SESSION")  # Windows Terminal
                or os.environ.get("ANSICON")  # ANSICON
                or "256color" in term
                or os.environ.get("TERM_PROGRAM") == "vscode"
            )

        return True

    def _colorize(self, text: str, color: str) -> str:
        """Apply color to text if colors are enabled."""
        if not self.enabled:
            return text
        return f"{color}{text}{self.RESET}"

    # Basic colors
    def red(self, text: str) -> str:
        """Red text (errors, warnings)."""
        return self._colorize(text, self.RED)

    def green(self, text: str) -> str:
        """Green text (success, found items)."""
        return self._colorize(text, self.GREEN)

    def yellow(self, text: str) -> str:
        """Yellow text (context, warnings)."""
        return self._colorize(text, self.YELLOW)

    def blue(self, text: str) -> str:
        """Blue text."""
        return self._colorize(text, self.BLUE)

    def magenta(self, text: str) -> str:
        """Magenta text (types, decorators)."""
        return self._colorize(text, self.MAGENTA)

    def cyan(self, text: str) -> str:
        """Cyan text (line numbers, file paths)."""
        return self._colorize(text, self.CYAN)

    def white(self, text: str) -> str:
        """White text."""
        return self._colorize(text, self.WHITE)

    # Bright colors
    def bright_green(self, text: str) -> str:
        """Bright green text."""
        return self._colorize(text, self.BRIGHT_GREEN)

    def bright_yellow(self, text: str) -> str:
        """Bright yellow text."""
        return self._colorize(text, self.BRIGHT_YELLOW)

    def bright_cyan(self, text: str) -> str:
        """Bright cyan text."""
        return self._colorize(text, self.BRIGHT_CYAN)

    # Styles
    def bold(self, text: str) -> str:
        """Bold text."""
        return self._colorize(text, self.BOLD)

    def dim(self, text: str) -> str:
        """Dim text (less prominent)."""
        return self._colorize(text, self.DIM)

    # Combined styles
    def success(self, text: str) -> str:
        """Success message (bold green)."""
        if not self.enabled:
            return text
        return f"{self.BOLD}{self.GREEN}{text}{self.RESET}"

    def error(self, text: str) -> str:
        """Error message (bold red)."""
        if not self.enabled:
            return text
        return f"{self.BOLD}{self.RED}{text}{self.RESET}"

    def warning(self, text: str) -> str:
        """Warning message (yellow)."""
        return self.yellow(text)

    def info(self, text: str) -> str:
        """Info message (cyan)."""
        return self.cyan(text)


# Global instance for convenience (thread-safe singleton)
_colors = None
_colors_lock = threading.Lock()


def get_colors(no_color: bool = False) -> Colors:
    """Get a Colors instance, optionally disabling colors.

    Thread-safe singleton pattern: the global instance is created once
    and reused across all threads.

    Args:
        no_color: If True, return a new disabled Colors instance
                  (not cached, allows per-call override).

    Returns:
        Colors instance configured appropriately.
    """
    global _colors

    # For no_color=True, always return a fresh disabled instance
    # This allows callers to override colors on a per-call basis
    if no_color:
        return Colors(enabled=False)

    # Double-checked locking pattern for thread-safe lazy initialization
    if _colors is None:
        with _colors_lock:
            # Check again inside the lock (another thread may have initialized)
            if _colors is None:
                _colors = Colors()
    return _colors
