"""Cantai commands: cantai-language (read or set the language Cantai sings a score in)."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ai_score_editing.sibelius import cantai_settings, launcher, service
from ai_score_editing.sibelius.commands._common import EXIT_COMMAND_FAILED, EXIT_OK


def register(sub: Any) -> dict[str, Callable[..., Any]]:
    lang = sub.add_parser(
        "cantai-language",
        help="read or set the language Cantai sings a score in (one language for every part)",
        description=(
            "Cantai stores one language per Sibelius score in its own settings file, keyed by the "
            "score's id. With no LANGUAGE, print the active score's id and language (Sibelius "
            "running, score open; or pass --score-id). With LANGUAGE, set it: Sibelius must be "
            "quit (Cantai reads the setting at start-up), so first note the score id, quit "
            "Sibelius, run this with --score-id, reopen the score and wait for Cantai's "
            "'Rendering N items' to finish before exporting. Cantai cannot sing different "
            "languages on different staves of one score. Codes: "
            + ", ".join(f"{code} ({name})" for code, name in cantai_settings.LANGUAGES.items())
        ),
    )
    lang.add_argument("language", nargs="?", help="language code or name: en, la, es, Latin, ...")
    lang.add_argument("--score-id", help="Sibelius score id (GUID); default: the score Sibelius has active")
    lang.add_argument(
        "--default", action="store_true",
        help="also make it Cantai's default for scores it has not seen yet",
    )
    lang.add_argument("--dry-run", action="store_true", help="show what would change; write nothing")
    # Test seams (default: the real files under ~/Library); hidden from --help.
    lang.add_argument("--settings", type=Path, help=argparse.SUPPRESS)
    lang.add_argument("--export-config", type=Path, help=argparse.SUPPRESS)
    return {"cantai-language": _run_cantai_language}


def _run_cantai_language(args: argparse.Namespace) -> int:
    try:
        return _cantai_language(args)
    except cantai_settings.CantaiSettingsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED


def _cantai_language(args: argparse.Namespace) -> int:
    settings_path = args.settings or cantai_settings.SETTINGS_PATH
    export_config = args.export_config or cantai_settings.SIBELIUS_EXPORT_CONFIG
    score_name = ""
    if args.score_id:
        score_id = cantai_settings.check_score_id(args.score_id)
    else:
        active = cantai_settings.read_active_score(export_config)
        if active is None:
            raise cantai_settings.CantaiSettingsError(
                "no active score: open the score in Sibelius and run this again to read its id, "
                "or pass --score-id"
            )
        score_id, score_name = active.score_id, active.score_name
    text = cantai_settings.read_settings(settings_path)
    current = cantai_settings.score_language(text, score_id)
    default = cantai_settings.default_language(text)
    report: dict[str, Any] = {
        "scoreId": score_id,
        "scoreName": score_name,
        "language": current,
        "defaultLanguage": default,
    }
    if not args.language:
        _print(args, report, _describe(report))
        return EXIT_OK

    code = cantai_settings.normalize_language(args.language)
    new_text = cantai_settings.set_score_language(text, score_id, code, also_default=args.default)
    report.update({"newLanguage": code, "changed": new_text != text, "dryRun": bool(args.dry_run)})
    if args.dry_run or new_text == text:
        verb = "would set" if args.dry_run and new_text != text else "already"
        _print(args, report, f"{_describe(report)}\n{verb} {code}")
        return EXIT_OK
    if launcher.is_sibelius_running():
        raise cantai_settings.CantaiSettingsError(
            "Sibelius is running: Cantai ignores the change until Sibelius restarts and may write its "
            f"own value over it. Quit Sibelius, then run: sibelius-cli cantai-language {code} "
            f"--score-id {score_id}"
        )
    backup_dir = service.backup_folder(getattr(args, "backup_dir", None))
    backup = cantai_settings.write_settings(new_text, settings_path, backup_dir)
    report["backup"] = str(backup)
    _print(
        args, report,
        f"{_describe(report)}\nset {code} (backup: {backup}). Open the score in Sibelius and wait for "
        "'Rendering N items' to clear from the status bar before exporting audio.",
    )
    return EXIT_OK


def _describe(report: dict[str, Any]) -> str:
    name = f" ({report['scoreName']})" if report.get("scoreName") else ""
    lang = report["language"] or f"none stored; Cantai's default {report['defaultLanguage']} applies"
    return f"score {report['scoreId']}{name}: Cantai language {lang}"


def _print(args: argparse.Namespace, report: dict[str, Any], human: str) -> None:
    print(json.dumps(report) if getattr(args, "json", False) else human)
