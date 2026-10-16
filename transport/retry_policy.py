"""Bounded retry policy."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Retry settings where ``max_retries`` excludes the initial attempt."""

    max_retries: int = 3

    def __post_init__(self) -> None:
        if isinstance(self.max_retries, bool) or not isinstance(self.max_retries, int):
            raise TypeError("max_retries must be an integer")
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")

    @property
    def max_attempts(self) -> int:
        """Total transmission attempts allowed per hop (initial + retries)."""
        return self.max_retries + 1
