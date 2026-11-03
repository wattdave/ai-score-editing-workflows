import sys


def main() -> None:
    from ai_score_editing.sibelius.cli import main as cli_main

    sys.exit(cli_main())

