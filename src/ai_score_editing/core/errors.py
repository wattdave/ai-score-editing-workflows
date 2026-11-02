"""Exception base classes shared by every back end."""

from __future__ import annotations


class ScoreEditingError(ValueError):
    """Base class for errors this package reports about a request (not an editor failure)."""


class BatchError(ScoreEditingError):
    """A batch is malformed, unsupported, or cannot be run against the score."""


class QueryError(ScoreEditingError):
    """A query selector is malformed, names an unreadable property or an unknown staff."""
