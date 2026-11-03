"""Cross-module invariants that outlived the import-path shims."""


def test_error_hierarchy():
    from ai_score_editing.core.errors import BatchError, ScoreEditingError
    from ai_score_editing.dorico.score import DoricoBatchError
    from ai_score_editing.musescore.score import MuseScoreBatchError
    from ai_score_editing.core.errors import QueryError

    assert issubclass(BatchError, ScoreEditingError) and issubclass(ScoreEditingError, ValueError)
    assert issubclass(DoricoBatchError, BatchError)
    assert issubclass(MuseScoreBatchError, BatchError)
    assert issubclass(QueryError, ScoreEditingError)
