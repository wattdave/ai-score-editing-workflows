"""Static linter for Sibelius ManuScript (.plg) files.

Validates object model property and method accesses using type inference
and type guards, matching the official Sibelius ManuScript Language Guide.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class LintIssue:
    """A lint issue discovered in a ManuScript file."""
    line: int
    column: int
    severity: str  # "error" or "warning"
    method_name: str
    message: str
    code_line: str
    variable: str | None = None
    inferred_type: str | None = None
    member: str | None = None
    hint: str | None = None

    def __str__(self) -> str:
        loc = f"Line {self.line}"
        if self.method_name:
            loc += f" in {self.method_name}()"
        out = f"[{self.severity.upper()}] {loc}: {self.message}"
        if self.hint:
            out += f"\n  Hint: {self.hint}"
        if self.code_line:
            out += f"\n  > {self.code_line.strip()}"
        return out


# ManuScript Object Model Definitions
# Base classes
BAR_OBJECT_VARIABLES = {
    "canbeinmultiplevoices", "color", "coloralpha", "colorred", "colorgreen",
    "colorblue", "cuesize", "dx", "dy", "hidden", "parentbar", "position", "selected",
    "type", "voicenumber",
}

BAR_OBJECT_METHODS = {
    "delete", "deselect", "freezemagneticlayoutpositions", "getisinvoice",
    "getplayedonnthpass", "nextitem", "previousitem", "removevoice",
    "resetposition", "resetdesign", "select", "setallvoices", "setvoice",
    "showinall", "showinparts", "showinscore", "setplayedonnthpass", "timeonnthpass",
}

# Derived classes and standalone types
OBJECT_MODEL: dict[str, dict[str, set[str]]] = {
    "BarObject": {
        "variables": set(BAR_OBJECT_VARIABLES),
        "methods": set(BAR_OBJECT_METHODS),
        "bases": set(),
    },
    "LyricItem": {
        "variables": {
            "duration", "numnotes", "styleastext", "styleid",
            "syllabletype", "text",
        },
        "methods": set(),
        "bases": {"BarObject"},
    },
    "NoteRest": {
        "variables": {
            "beam", "duration", "hasficta", "gracenote", "notecount",
            "singlevoiceaccidental", "voicenumber",
        },
        "methods": {
            "addacciaccaturabefore", "addappoggiaturabefore", "addnote",
            "delete", "flipstem", "getarticulation", "setarticulation",
            "gethasaccidental", "sethasaccidental",
        },
        "bases": {"BarObject"},
    },
    "Note": {
        "variables": {
            "accidental", "accidentalstyle", "diatonicpitch", "duration",
            "name", "noterest", "pitch", "position", "tied", "tiedirection",
            "writtenpitch",
        },
        "methods": set(),
        "bases": set(),
    },
    "KeySignature": {
        "variables": {"astext", "major", "sharps"},
        "methods": set(),
        "bases": {"BarObject"},
    },
    "TimeSignature": {
        "variables": {"allowcautionary", "denominator", "numerator", "text"},
        "methods": set(),
        "bases": {"BarObject"},
    },
    "Clef": {
        "variables": {"astext", "styleid"},
        "methods": set(),
        "bases": {"BarObject"},
    },
    "Text": {
        "variables": {
            "erasebackground", "erasebackgroundoverridden", "initialfontname",
            "initialfontsize", "jumpatendofbar", "styleastext", "styleid",
            "text", "textwithformatting", "textwithformattingasstring",
        },
        "methods": set(),
        "bases": {"BarObject"},
    },
    "SystemTextItem": {
        "variables": {
            "erasebackground", "erasebackgroundoverridden", "initialfontname",
            "initialfontsize", "jumpatendofbar", "styleastext", "styleid",
            "text", "textwithformatting", "textwithformattingasstring",
        },
        "methods": set(),
        "bases": {"BarObject"},
    },
    "Score": {
        "variables": {
            "arranger", "artist", "autooptimizeenabled", "barlines",
            "barplaybackorder", "barplaybackorderstring", "bracketsandbraces",
            "composer", "composerdates", "copyist", "copyright",
            "currentdynamicpart", "currentplaybackposition", "documentsetup",
            "engravingrules", "filename", "focusonstaves", "hitpoints",
            "instrumenttypes", "istransposingscore", "keysignatureat",
            "lyricist", "mainmusicfontname", "maintextfontname",
            "musictextfontname", "pagecount", "playbacklineposition",
            "publisher", "redohistory", "scoreduration", "selection",
            "staffcount", "systemobjectpositions", "systemstaff",
            "timesignatureat", "title", "transposingscore", "undohistory",
            "unitname", "versionhistory",
        },
        "methods": {
            "addstaff", "applystyle", "clearredohistory", "clearundohistory",
            "createinstrument", "createinstrumentatstaff",
            "exportcurrentplaybackposition", "extractparts",
            "getactiveplaybackconfiguration", "getdynamicparts", "getversions",
            "importhousestyle", "insertbar", "insertbars", "nthstaff",
            "optimizestaffspacing", "playlivetempo", "removeallhighlights",
            "removevideo", "renametextstyle", "save", "saveas",
            "saveasearlierversion", "savecopyas", "setplaybackpos",
            "showemptystaves", "stavetypeid", "systemcount", "symbolexists",
            "symbolindex", "textstyleid", "viewlivetempo",
        },
        "bases": set(),
    },
    "Bar": {
        "variables": {
            "barcount", "barnumber", "length", "parentstaff",
            "rhythmiclength", "splitbar", "timesignature",
        },
        "methods": {
            "addbarrest", "addclef", "addcomment", "addguitarframe",
            "addguitarscalediagram", "addinstrumentchange", "addkeysignature",
            "addline", "addlyric", "addnote", "addnoterest",
            "addrehearsalmark", "addspecialbarline", "addsymbol", "addsystemsymbol", "addsystemtext",
            "addtext", "addtimesignature", "addtuplet", "clear", "delete",
            "getendtime", "getstarttime", "insertbarrest", "nthobject",
        },
        "bases": set(),
    },
    "SpecialBarline": {
        "variables": {"barlinetype", "barlineinternaltype"},
        "methods": set(),
        "bases": {"BarObject"},
    },
    "Staff": {
        "variables": {
            "barcount", "fullinstrumentname", "fullstaffname", "initialclefstyle",
            "initialclefstyleid", "initialinstrumenttype", "initialkeysignature",
            "initialstyleid", "instrumentname", "issystemstaff", "isvocalstaff",
            "parentscore", "shortinstrumentname", "shortstaffname", "staffnum",
        },
        "methods": {"nthbar"},
        "bases": set(),
    },
    "SystemStaff": {
        "variables": {"barcount", "parentscore"},
        "methods": {"nthbar"},
        "bases": set(),
    },
    "Selection": {
        "variables": {
            "firstbarnumber", "lastbarnumber", "topstaff", "bottomstaff",
            "ispassage", "staffcount",
        },
        "methods": {"clear", "selectpassage"},
        "bases": set(),
    },
    "Dictionary": {
        "variables": set(),
        "methods": {
            "push", "pop", "get", "set", "contains", "getkeys", "getvalues", "length",
        },
        "bases": set(),
    },
    "SparseArray": {
        "variables": set(),
        "methods": {
            "push", "pop", "insert", "remove", "length",
        },
        "bases": set(),
    },
    "Sibelius": {
        "variables": {
            "activescore", "scorecount", "earlierversionnames", "fontfamilies",
            "programversion", "version",
        },
        "methods": {
            "findcommandid", "execute", "messagebox", "open", "new",
            "createdictionary", "createsparsearray", "nthscore",
            "isfontfamilyinstalled",
        },
        "bases": set(),
    },
}


def _get_all_valid_members(type_name: str) -> set[str]:
    """Recursively collect all valid variables and methods for a type."""
    type_info = OBJECT_MODEL.get(type_name)
    if not type_info:
        return set()
    members = set(type_info["variables"]) | set(type_info["methods"])
    for base in type_info["bases"]:
        members |= _get_all_valid_members(base)
    return members


def _find_type_providing_member(member: str) -> list[str]:
    """Find all types in the object model that define a given member."""
    lowered = member.lower()
    matches = []
    for t_name, info in OBJECT_MODEL.items():
        if lowered in info["variables"] or lowered in info["methods"]:
            matches.append(t_name)
    return matches


class ManuScriptLinter:
    """Performs static linting on ManuScript files."""

    def __init__(self) -> None:
        self.issues: list[LintIssue] = []

    def lint_file(self, file_path: str | Path) -> list[LintIssue]:
        path = Path(file_path)
        content = path.read_text(encoding="utf-8", errors="replace")
        return self.lint_code(content, str(path))

    def lint_code(self, code: str, filename: str = "<code string>") -> list[LintIssue]:
        self.issues = []
        lines = code.splitlines()

        # Check basic balanced braces
        open_braces = 0
        for idx, line in enumerate(lines, start=1):
            stripped = self._strip_comments_and_strings(line)
            open_braces += stripped.count("{") - stripped.count("}")

        if open_braces != 0:
            self.issues.append(
                LintIssue(
                    line=len(lines),
                    column=1,
                    severity="error",
                    method_name="",
                    message=f"Unbalanced braces in file (net brace count: {open_braces})",
                    code_line="",
                )
            )

        # Parse methods: MethodName "(args) { ... }"
        method_pattern = re.compile(r'^\s*([A-Za-z0-9_]+)\s+"(\([^)]*\))\s*\{')

        current_method: str | None = None
        current_method_start_line = 1
        method_lines: list[tuple[int, str]] = []
        method_brace_depth = 0

        for line_no, raw_line in enumerate(lines, start=1):
            if current_method is None:
                match = method_pattern.match(raw_line)
                if match:
                    current_method = match.group(1)
                    current_method_start_line = line_no
                    method_lines = [(line_no, raw_line)]
                    stripped = self._strip_comments_and_strings(raw_line)
                    method_brace_depth = stripped.count("{") - stripped.count("}")
            else:
                method_lines.append((line_no, raw_line))
                stripped = self._strip_comments_and_strings(raw_line)
                method_brace_depth += stripped.count("{") - stripped.count("}")
                # ManuScript methods end with }" at line boundary or balanced brace
                if method_brace_depth <= 0 or re.search(r'\}"\s*;?\s*$', raw_line):
                    self._lint_method(current_method, method_lines)
                    current_method = None
                    method_lines = []
                    method_brace_depth = 0

        # If a method remained unclosed
        if current_method and method_lines:
            self._lint_method(current_method, method_lines)

        return sorted(self.issues, key=lambda x: (x.line, x.column))

    def _strip_comments_and_strings(self, line: str) -> str:
        """Strip inline comments and string literals to avoid false positive brace counts."""
        # Strip single line comments //
        line = re.sub(r'//.*$', '', line)
        # Strip string literals '...' and "..."
        line = re.sub(r"'[^']*'", "''", line)
        line = re.sub(r'"[^"]*"', '""', line)
        return line

    def _lint_method(self, method_name: str, lines: list[tuple[int, str]]) -> None:
        """Analyze a single method for type guards and invalid member accesses."""
        # Scope stack: list of dicts mapping variable_name -> type_name
        scope_stack: list[dict[str, str]] = [{}]

        # Standard known globals
        scope_stack[0]["sibelius"] = "Sibelius"

        for line_no, raw_line in lines:
            line = raw_line.strip()
            stripped = self._strip_comments_and_strings(line)

            # Check for block entries / exits
            closing_count = stripped.count("}")
            for _ in range(closing_count):
                if len(scope_stack) > 1:
                    scope_stack.pop()

            opening_count = stripped.count("{")
            for _ in range(opening_count):
                # Copy current scope to new block level
                scope_stack.append(dict(scope_stack[-1]))

            current_scope = scope_stack[-1]

            # Sibelius cannot parse chained subscripts (a[i]['k']); it raises
            # a modal parse error only when the method is first called.
            if "][" in stripped.replace(" ", ""):
                self.issues.append(LintIssue(
                    line=line_no,
                    column=1,
                    severity="error",
                    method_name=method_name,
                    message="Chained subscript is a ManuScript parse error",
                    code_line=raw_line,
                    hint="Assign the first subscript to a variable, then index that",
                ))

            # 1. Detect assignments from known factory functions / properties
            # score = RequireScore(); or score = Sibelius.ActiveScore;
            m_score = re.search(r'\b([A-Za-z0-9_]+)\s*=\s*(?:RequireScore\(\)|Sibelius\.ActiveScore)\b', line, re.IGNORECASE)
            if m_score:
                current_scope[m_score.group(1).lower()] = "Score"

            # systemStaff = score.SystemStaff;
            m_sys = re.search(r'\b([A-Za-z0-9_]+)\s*=\s*([A-Za-z0-9_]+)\.SystemStaff\b', line, re.IGNORECASE)
            if m_sys and current_scope.get(m_sys.group(2).lower()) == "Score":
                current_scope[m_sys.group(1).lower()] = "SystemStaff"

            # bar = staff.NthBar(...) or bar = systemStaff.NthBar(...)
            m_bar = re.search(r'\b([A-Za-z0-9_]+)\s*=\s*([A-Za-z0-9_]+)\.NthBar\(', line, re.IGNORECASE)
            if m_bar and current_scope.get(m_bar.group(2).lower()) in {"Staff", "SystemStaff"}:
                current_scope[m_bar.group(1).lower()] = "Bar"

            # 2. Detect typed loop declarations:
            # for each KeySignature ks in bar {
            m_loop = re.search(r'\bfor\s+each\s+([A-Za-z0-9_]+)\s+([A-Za-z0-9_]+)\s+in\b', line, re.IGNORECASE)
            if m_loop:
                declared_type = m_loop.group(1)
                var_name = m_loop.group(2).lower()
                for known_type in OBJECT_MODEL:
                    if known_type.lower() == declared_type.lower():
                        current_scope[var_name] = known_type
                        break

            # 3. Detect type-guard conditions:
            # if (obj.Type = 'LyricItem') or if (obj.Type == "NoteRest")
            m_guard = re.search(
                r'\bif\s*\(\s*([A-Za-z0-9_]+)\.Type\s*={1,2}\s*[\'"]([A-Za-z0-9_]+)[\'"]\s*\)',
                line,
                re.IGNORECASE,
            )
            if m_guard:
                var_name = m_guard.group(1).lower()
                target_type = m_guard.group(2)
                for known_type in OBJECT_MODEL:
                    if known_type.lower() == target_type.lower():
                        current_scope[var_name] = known_type
                        break

            # 4. Check member accesses: <var>.<Member>
            member_matches = list(re.finditer(r'\b([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)\b', line))
            for m in member_matches:
                var_name = m.group(1).lower()
                member_name = m.group(2)

                # Skip if member is 'Type' (universal guard)
                if member_name.lower() == "type":
                    continue

                inferred_type = current_scope.get(var_name)
                if not inferred_type or inferred_type not in OBJECT_MODEL:
                    continue

                valid_members = _get_all_valid_members(inferred_type)
                if member_name.lower() not in valid_members:
                    col = m.start(2) + 1
                    providers = _find_type_providing_member(member_name)
                    hint = None
                    if providers:
                        hint = f"'{member_name}' exists on: {', '.join(providers)}"

                    self.issues.append(
                        LintIssue(
                            line=line_no,
                            column=col,
                            severity="error",
                            method_name=method_name,
                            message=(
                                f"No field or method named '{member_name}' on type '{inferred_type}' "
                                f"(accessed via '{m.group(1)}.{member_name}')"
                            ),
                            code_line=raw_line,
                            variable=m.group(1),
                            inferred_type=inferred_type,
                            member=member_name,
                            hint=hint,
                        )
                    )


def lint_manuscript(code: str) -> list[LintIssue]:
    """Lint ManuScript code string and return list of issues."""
    return ManuScriptLinter().lint_code(code)


def lint_file(path: str | Path) -> list[LintIssue]:
    """Lint a .plg file and return list of issues."""
    return ManuScriptLinter().lint_file(path)
