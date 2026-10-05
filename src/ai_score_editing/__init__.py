import sys


def main() -> None:
    from ai_score_editing.cli import main as cli_main

    sys.exit(cli_main())
