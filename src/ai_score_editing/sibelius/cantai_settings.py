"""Read and set the language Cantai sings a Sibelius score in.

Cantai (the singing-voice plug-in) keeps one language per score, for every part of
that score, in its own settings file (a JUCE properties file, XML):

    ~/Library/Application Support/Cantai/Cantai.settings
        <VALUE name="scoreLanguage" val="la"/>            default for scores with no entry
        <VALUE name="sibLang_<md5(scoreId)>" val="es"/>   one per Sibelius score

``scoreId`` is the GUID Sibelius stores in the score (copies of a .sib share it).
While a score is active Sibelius names it in
``~/Library/Application Support/Avid/Sibelius/playback-data-export-config.json``
(``activeScore.scoreId``); after Sibelius quits ``activeScore`` is null.

Cantai reads the file when Sibelius starts and ignores edits made while it runs, so
a new language is set with Sibelius quit and takes effect when the score is opened
again: Cantai then re-renders every part (Sibelius's status bar shows "Rendering N
items"). Tested 2026-11-25 with Cantai 4.0.2 and Sibelius 26.11: see
docs/cantai-language.md. The per-instance ``scoreLanguage`` in the playback
configuration's ``Cantai data/*.fxb`` files is not used for this.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

SETTINGS_PATH = Path.home() / "Library/Application Support/Cantai/Cantai.settings"
SIBELIUS_EXPORT_CONFIG = (
    Path.home() / "Library/Application Support/Avid/Sibelius/playback-data-export-config.json"
)

#: Codes Cantai 4.0.2's language menu offers (its plug-in UI); "ja" is hidden there.
LANGUAGES: dict[str, str] = {
    "en": "English (US)",
    "en-GB": "English (UK), experimental",
    "es": "Spanish",
    "la": "Latin",
    "it": "Italian, experimental",
    "pt-PT": "Portuguese (Portugal), experimental",
    "pt-BR": "Portuguese (Brazil), experimental",
    "ja": "Japanese, experimental, hidden in Cantai's menu",
}
LANGUAGE_ALIASES = {"english": "en", "latin": "la", "spanish": "es", "italian": "it"}

_GUID = re.compile(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$")


class CantaiSettingsError(Exception):
    pass


@dataclass(frozen=True)
class ActiveScore:
    score_id: str
    score_name: str


def normalize_language(value: str) -> str:
    """Return Cantai's code for ``value`` (a code such as ``la`` or a name such as ``Latin``)."""
    text = value.strip()
    alias = LANGUAGE_ALIASES.get(text.lower())
    if alias:
        return alias
    for code in LANGUAGES:
        if code.lower() == text.lower():
            return code
    raise CantaiSettingsError(
        f"unknown Cantai language {value!r}; use one of: {', '.join(LANGUAGES)}"
    )


def check_score_id(score_id: str) -> str:
    if not _GUID.match(score_id.strip()):
        raise CantaiSettingsError(f"not a Sibelius score id (GUID): {score_id!r}")
    return score_id.strip()


def score_key(score_id: str) -> str:
    """The settings key Cantai uses for a Sibelius score's language."""
    return "sibLang_" + hashlib.md5(check_score_id(score_id).encode("utf-8")).hexdigest()


def read_active_score(config_path: Path = SIBELIUS_EXPORT_CONFIG) -> ActiveScore | None:
    """The score Sibelius has active, from its playback-data export config, or None."""
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise CantaiSettingsError(f"cannot read {config_path}: {exc}") from exc
    active = data.get("activeScore") if isinstance(data, dict) else None
    if not isinstance(active, dict) or not active.get("scoreId"):
        return None
    return ActiveScore(str(active["scoreId"]), str(active.get("scoreName") or ""))


def _value_pattern(name: str) -> re.Pattern[str]:
    return re.compile(r'(<VALUE name="%s" val=")([^"]*)("\s*/>)' % re.escape(name))


def read_value(text: str, name: str) -> str | None:
    match = _value_pattern(name).search(text)
    return match.group(2) if match else None


def score_language(text: str, score_id: str) -> str | None:
    """The language stored for ``score_id``, or None (Cantai then uses the default)."""
    return read_value(text, score_key(score_id))


def default_language(text: str) -> str | None:
    return read_value(text, "scoreLanguage")


def set_value(text: str, name: str, value: str) -> str:
    """Set ``<VALUE name=... val=...>`` in a JUCE properties file, adding it if missing."""
    pattern = _value_pattern(name)
    if pattern.search(text):
        return pattern.sub(lambda m: m.group(1) + value + m.group(3), text, count=1)
    match = re.search(r"<PROPERTIES>(\r?\n)", text)
    if not match:
        raise CantaiSettingsError("Cantai.settings has no <PROPERTIES> element")
    newline = match.group(1)
    entry = f'  <VALUE name="{name}" val="{value}"/>{newline}'
    return text[: match.end()] + entry + text[match.end():]


def set_score_language(text: str, score_id: str, language: str, *, also_default: bool = False) -> str:
    code = normalize_language(language)
    text = set_value(text, score_key(score_id), code)
    if also_default:
        text = set_value(text, "scoreLanguage", code)
    return text


def read_settings(path: Path = SETTINGS_PATH) -> str:
    try:
        with open(path, encoding="utf-8", newline="") as handle:
            return handle.read()
    except FileNotFoundError as exc:
        raise CantaiSettingsError(f"{path} not found: is Cantai installed and has it run once?") from exc


def write_settings(text: str, path: Path = SETTINGS_PATH, backup_dir: Path | None = None) -> Path:
    """Back up ``path`` (to ``backup_dir`` or next to it), then replace it atomically.

    Returns the backup's path."""
    target_dir = backup_dir or path.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    backup = target_dir / f"{path.name}.{time.strftime('%Y%m%d-%H%M%S')}.bak"
    shutil.copy2(path, backup)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".Cantai.settings.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return backup
