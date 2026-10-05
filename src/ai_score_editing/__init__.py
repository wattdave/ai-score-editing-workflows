import sys


def main() -> None:
    from ai_score_editing.sibelius.cli import main as cli_main

    sys.exit(cli_main())


def deprecated_main() -> None:
    print(
        "sibelius-websocket-cli is deprecated and will be removed; use sibelius-cli.",
        file=sys.stderr,
    )
    main()
