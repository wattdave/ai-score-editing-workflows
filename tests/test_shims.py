"""Old module paths stay importable and expose the public names of their new homes."""

import importlib

import pytest

def _public(module) -> set[str]:
    return {name for name in vars(module) if not name.startswith("_")}


def test_batch_ops_reexports_schema_and_sibelius_names():
    batch_ops = importlib.import_module("ai_score_editing.batch_ops")
    schema = importlib.import_module("ai_score_editing.core.batch_schema")
    sibelius = importlib.import_module("ai_score_editing.sibelius.batch_ops")
    for name in _public(schema) - {"validate_batch"}:
        assert getattr(batch_ops, name) is getattr(schema, name)
    for name in _public(sibelius):
        assert getattr(batch_ops, name) is getattr(sibelius, name)
    assert batch_ops.BatchError is importlib.import_module("ai_score_editing.core.errors").BatchError


def test_error_hierarchy():
    from ai_score_editing.core.errors import BatchError, ScoreEditingError
    from ai_score_editing.dorico.score import DoricoBatchError
    from ai_score_editing.musescore.score import MuseScoreBatchError
    from ai_score_editing.query import QueryError

    assert issubclass(BatchError, ScoreEditingError) and issubclass(ScoreEditingError, ValueError)
    assert issubclass(DoricoBatchError, BatchError)
    assert issubclass(MuseScoreBatchError, BatchError)
    assert issubclass(QueryError, ScoreEditingError)
