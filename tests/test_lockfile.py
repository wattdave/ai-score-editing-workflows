"""uv.lock must resolve from public PyPI so anyone can run `uv sync`."""

import tomllib
from pathlib import Path

LOCK = Path(__file__).resolve().parent.parent / "uv.lock"
PUBLIC = ("https://pypi.org/simple", "https://files.pythonhosted.org/")


def test_lockfile_uses_public_pypi():
    lock = tomllib.loads(LOCK.read_text())
    private = []
    for pkg in lock["package"]:
        registry = pkg.get("source", {}).get("registry")
        if registry and registry != PUBLIC[0]:
            private.append(f"{pkg['name']}: {registry}")
        for art in ([pkg["sdist"]] if "sdist" in pkg else []) + pkg.get("wheels", []):
            if not art["url"].startswith(PUBLIC):
                private.append(f"{pkg['name']}: {art['url']}")
    assert not private, (
        "uv.lock points at a private package index; relock against public PyPI:\n"
        + "\n".join(private[:10])
    )
