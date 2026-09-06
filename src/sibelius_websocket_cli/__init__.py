import sys


def main() -> None:
    from sibelius_websocket_cli.cli import main as cli_main

    sys.exit(cli_main())
