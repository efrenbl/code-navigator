"""Sample Python file for testing the code mapper.

This module contains various Python constructs to test symbol detection.
"""

# Constants
MAX_RETRIES = 3
DEFAULT_TIMEOUT = 30


def simple_function():
    """A simple function with no arguments."""
    return "Hello, World!"


def function_with_args(name: str, age: int = 0) -> str:
    """A function with typed arguments.

    Args:
        name: The person's name.
        age: The person's age.

    Returns:
        A greeting string.
    """
    return f"Hello, {name}! You are {age} years old."


async def async_function(url: str) -> dict:
    """An async function for testing.

    Args:
        url: The URL to fetch.

    Returns:
        Response data as a dict.
    """
    return {"url": url, "status": "ok"}


class SimpleClass:
    """A simple class with basic methods."""

    def __init__(self, value: int):
        """Initialize the class.

        Args:
            value: Initial value.
        """
        self.value = value

    def get_value(self) -> int:
        """Get the current value."""
        return self.value

    def set_value(self, value: int) -> None:
        """Set a new value.

        Args:
            value: The new value.
        """
        self.value = value


class DerivedClass(SimpleClass):
    """A class that inherits from SimpleClass."""

    def __init__(self, value: int, name: str):
        """Initialize with value and name."""
        super().__init__(value)
        self.name = name

    def get_name(self) -> str:
        """Get the name."""
        return self.name


@staticmethod
def decorated_function():
    """A decorated function."""
    pass


class ClassWithDecorators:
    """A class with decorated methods."""

    @property
    def computed_value(self) -> int:
        """A computed property."""
        return 42

    @classmethod
    def create(cls, value: int) -> "ClassWithDecorators":
        """Factory method."""
        return cls()

    @staticmethod
    def utility() -> str:
        """A static utility method."""
        return "utility"


def function_with_dependencies():
    """A function that calls other functions.

    This is used to test dependency tracking.
    """
    result = simple_function()
    greeting = function_with_args("Test", 25)
    return f"{result} {greeting}"
