"""Old module paths stay importable and expose the public names of their new homes."""

import importlib

import pytest

def _public(module) -> set[str]:
    return {name for name in vars(module) if not name.startswith("_")}


def test_error_hierarchy():
    from ai_score_editing.core.errors import BatchError, ScoreEditingError
    from ai_score_editing.dorico.score import DoricoBatchError
    from ai_score_editing.musescore.score import MuseScoreBatchError
    from ai_score_editing.query import QueryError

    assert issubclass(BatchError, ScoreEditingError) and issubclass(ScoreEditingError, ValueError)
    assert issubclass(DoricoBatchError, BatchError)
    assert issubclass(MuseScoreBatchError, BatchError)
    assert issubclass(QueryError, ScoreEditingError)
