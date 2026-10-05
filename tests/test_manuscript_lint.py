"""Tests for the ManuScript static linter and regression checks."""

from pathlib import Path
from ai_score_editing.manuscript_linter import (
    ManuScriptLinter,
    lint_file,
    lint_manuscript,
)


def test_lint_current_sibwscli_plg() -> None:
    """The current active sibwscli.plg must have 0 lint errors."""
    plg_path = (
        Path(__file__).parent.parent
        / "src"
        / "ai_score_editing"
        / "manuscript"
        / "sibwscli.plg"
    )
    assert plg_path.exists(), f"Plug-in file not found at {plg_path}"
    issues = lint_file(plg_path)
    # If any issues are found, print them for easy debugging
    issue_strs = [str(i) for i in issues]
    assert not issues, f"Found lint issues in sibwscli.plg:\n" + "\n".join(issue_strs)


def test_regression_catches_initialfontname_on_lyricitem() -> None:
    """Verify that the linter catches the exact historical v13 failure.

    In bridge v13, ReadLyrics and DescribeObject accessed:
      obj.InitialFontName
      obj.InitialFontSize
      obj.TextWithFormattingAsString
    on LyricItem, which caused Sibelius to throw runtime error dialogs:
      No field named "InitialFontName"
    """
    historical_faulty_code = """
{
    DescribeObject "(obj, index) {
        if (obj.Type = 'LyricItem') {
            syllableType = 'end';
            if (obj.SyllableType = MiddleOfWord) {
                syllableType = 'middle';
            }
            return CreateDictionary(
                'index', index,
                'type', obj.Type,
                'position', obj.Position,
                'voice', obj.VoiceNumber,
                'text', obj.Text,
                'syllableType', syllableType,
                'styleId', '' & obj.StyleId,
                'styleAsText', '' & obj.StyleAsText,
                'initialFontName', '' & obj.InitialFontName,
                'initialFontSize', obj.InitialFontSize,
                'textWithFormatting', '' & obj.TextWithFormattingAsString);
        }
        return null;
    }"
}
"""
    issues = lint_manuscript(historical_faulty_code)
    assert len(issues) == 3, f"Expected exactly 3 issues, got {len(issues)}: {[str(i) for i in issues]}"

    members_flagged = [i.member for i in issues]
    assert "InitialFontName" in members_flagged
    assert "InitialFontSize" in members_flagged
    assert "TextWithFormattingAsString" in members_flagged

    # Check that hints correctly point out where these fields actually belong
    for issue in issues:
        assert issue.inferred_type == "LyricItem"
        assert issue.severity == "error"
        assert "Text" in issue.hint or "SystemTextItem" in issue.hint
        assert "No field or method named" in issue.message


def test_lint_typed_loops_and_inheritance() -> None:
    """Verify that inheritance from BarObject is respected and typed loops are checked."""
    code = """
{
    TestMethods "(bar) {
        for each KeySignature ks in bar {
            // AsText, Major, Sharps are on KeySignature
            name = ks.AsText;
            maj = ks.Major;
            // Position is inherited from BarObject
            pos = ks.Position;
            // Invalid property on KeySignature
            bad = ks.InitialFontName;
        }

        for each NoteRest nr in bar {
            // FlipStem is on NoteRest
            nr.FlipStem();
            // ResetDesign is inherited from BarObject
            nr.ResetDesign();
            // Invalid property on NoteRest
            bad2 = nr.Sharps;
        }
    }"
}
"""
    issues = lint_manuscript(code)
    assert len(issues) == 2, f"Expected 2 issues, got {len(issues)}: {[str(i) for i in issues]}"
    flagged = [(i.inferred_type, i.member) for i in issues]
    assert ("KeySignature", "InitialFontName") in flagged
    assert ("NoteRest", "Sharps") in flagged


def test_lint_score_methods_and_syntax() -> None:
    """Verify Score object methods and syntax checking."""
    valid_score_code = """
{
    GetInfo "() {
        score = Sibelius.ActiveScore;
        font = score.MainTextFontName;
        staves = score.StaffCount;
        return CreateDictionary('font', font, 'staves', staves);
    }"
}
"""
    assert not lint_manuscript(valid_score_code)

    invalid_score_code = """
{
    GetInfo "() {
        score = Sibelius.ActiveScore;
        // Non-existent property on Score
        foo = score.NonExistentField;
    }"
}
"""
    issues = lint_manuscript(invalid_score_code)
    assert len(issues) == 1
    assert issues[0].member == "NonExistentField"
    assert issues[0].inferred_type == "Score"


def test_lint_unbalanced_braces() -> None:
    """Unbalanced braces should be reported as syntax errors."""
    broken_code = """
{
    Method "() {
        if (True) {
            val = 1;
    }"
}
"""
    issues = lint_manuscript(broken_code)
    assert any("Unbalanced braces" in i.message for i in issues)


def test_lint_chained_subscript() -> None:
    """Sibelius rejects a[i]['k'] with a modal parse error at call time."""
    code = """
{
    Method "(where) {
        op = where[0]['op'];
        cond = where[0];
        return cond['op'];
    }"
}
"""
    issues = [i for i in lint_manuscript(code) if "Chained subscript" in i.message]
    assert [i.code_line.strip() for i in issues] == ["op = where[0]['op'];"]


def test_lint_double_quote_in_method_body() -> None:
    """A " in a method body, even in a comment, ends the method in Sibelius."""
    code = '''
{
    Method "() {
        // turn off "include all staves"
        return 1;
    }"
}
'''
    issues = lint_manuscript(code)
    assert any("double quote" in i.message and i.line == 4 for i in issues)
    assert not lint_manuscript(code.replace('"include all staves"', "'include all staves'"))
