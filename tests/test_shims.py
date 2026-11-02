"""Old module paths stay importable and expose the public names of their new homes."""

import importlib

import pytest

SHIMS = {
    "ai_score_editing.units": "ai_score_editing.core.units",
    "ai_score_editing.intervals": "ai_score_editing.core.intervals",
    "ai_score_editing.barrange": "ai_score_editing.core.barrange",
    "ai_score_editing.lyrics": "ai_score_editing.core.lyrics",
    "ai_score_editing.music": "ai_score_editing.core.music",
}


ALIASES = {
    "ai_score_editing.mix_proof": "ai_score_editing.workflows.mix_proof",
    "ai_score_editing.rehearsal_mix": "ai_score_editing.workflows.rehearsal_mix",
    "ai_score_editing.musicxml_round": "ai_score_editing.workflows.musicxml_round",
    "ai_score_editing.abc_notation": "ai_score_editing.workflows.abc_notation",
    "ai_score_editing.polychoral": "ai_score_editing.workflows.polychoral",
    "ai_score_editing.musicxml_split": "ai_score_editing.workflows.musicxml_split",
}
SPLIT_SUBMODULES = ["io", "lyrics", "model", "routing", "ties", "timeline", "validation", "profiles", "profiles.satb", "profiles.polychoral_16"]


def _public(module) -> set[str]:
    return {name for name in vars(module) if not name.startswith("_")}


@pytest.mark.parametrize("old,new", SHIMS.items())
def test_shim_exposes_new_home(old, new):
    old_module, new_module = importlib.import_module(old), importlib.import_module(new)
    missing = {n for n in _public(new_module) if not hasattr(old_module, n)}
    assert not missing, f"{old} lacks {sorted(missing)}"
    for name in _public(new_module):
        assert getattr(old_module, name) is getattr(new_module, name)


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


@pytest.mark.parametrize("old,new", ALIASES.items())
def test_workflow_alias_is_same_module(old, new):
    assert importlib.import_module(old) is importlib.import_module(new)


@pytest.mark.parametrize("sub", SPLIT_SUBMODULES)
def test_musicxml_split_submodules_resolve_to_same_objects(sub):
    old = importlib.import_module(f"ai_score_editing.musicxml_split.{sub}")
    new = importlib.import_module(f"ai_score_editing.workflows.musicxml_split.{sub}")
    assert old is new


def test_old_paths_work_in_from_imports_and_share_state(monkeypatch):
    from ai_score_editing import polychoral
    from ai_score_editing.musicxml_split.profiles.satb import split_satb
    from ai_score_editing.musicxml_split import io as old_io
    from ai_score_editing.workflows.musicxml_split import io as new_io
    from ai_score_editing.workflows.musicxml_split.profiles.satb import split_satb as new_split

    assert split_satb is new_split
    monkeypatch.setattr(old_io, "parse_musicxml", "patched")
    assert new_io.parse_musicxml == "patched"
    assert polychoral._clean_note is importlib.import_module("ai_score_editing.workflows.polychoral")._clean_note
