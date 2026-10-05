"""Utilities for detecting and launching Sibelius."""

from __future__ import annotations

import ipaddress
import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def is_local_host(host: str) -> bool:
    """Return True if host refers to the local machine."""
    if host.lower() in LOCAL_HOSTS:
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_loopback or ip.is_unspecified
    except ValueError:
        return False


def is_sibelius_running() -> bool:
    """Return True if a Sibelius process is currently running on the system."""
    if sys.platform == "darwin":
        return _is_sibelius_running_macos()
    elif sys.platform == "win32":
        return _is_sibelius_running_windows()
    else:
        return _is_sibelius_running_generic()


def _is_sibelius_running_macos() -> bool:
    try:
        res = subprocess.run(
            ["pgrep", "-i", "-x", "Sibelius"],
            capture_output=True,
            check=False,
        )
        if res.returncode == 0:
            return True
    except (FileNotFoundError, PermissionError):
        pass

    try:
        res = subprocess.run(
            ["osascript", "-e", 'application id "com.avid.sibelius" is running'],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip().lower() == "true":
            return True
    except (FileNotFoundError, PermissionError):
        pass

    return False


def _is_sibelius_running_windows() -> bool:
    try:
        res = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Sibelius.exe", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0 and "Sibelius.exe" in res.stdout:
            return True
    except (FileNotFoundError, PermissionError):
        pass
    return False


def _is_sibelius_running_generic() -> bool:
    try:
        res = subprocess.run(
            ["pgrep", "-i", "-x", "Sibelius"],
            capture_output=True,
            check=False,
        )
        return res.returncode == 0
    except (FileNotFoundError, PermissionError):
        return False


def find_sibelius_app(custom_path: str | Path | None = None) -> Path | None:
    """Locate Sibelius application executable or bundle."""
    if custom_path:
        p = Path(custom_path).expanduser().resolve()
        if p.exists():
            return p
        raise FileNotFoundError(f"Specified Sibelius path does not exist: {custom_path}")

    if sys.platform == "darwin":
        candidates = [
            Path("/Applications/Sibelius.app"),
            Path.home() / "Applications" / "Sibelius.app",
        ]
        for c in candidates:
            if c.exists():
                return c
    elif sys.platform == "win32":
        candidates = [
            Path(os.environ.get("ProgramFiles", "C:\\Program Files"))
            / "Avid"
            / "Sibelius"
            / "Sibelius.exe",
            Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"))
            / "Avid"
            / "Sibelius"
            / "Sibelius.exe",
        ]
        for c in candidates:
            if c.exists():
                return c
    return None


def launch_sibelius(app_path: str | Path | None = None) -> None:
    """Launch the Sibelius application process in the background."""
    resolved = find_sibelius_app(app_path)
    logger.info("Launching Sibelius (path: %s)...", resolved or app_path or "default")

    if sys.platform == "darwin":
        target = str(resolved) if resolved else "Sibelius"
        subprocess.Popen(["open", "-a", target])
    elif sys.platform == "win32":
        if resolved:
            try:
                os.startfile(str(resolved))  # type: ignore[attr-defined]
            except AttributeError:
                subprocess.Popen([str(resolved)])
        else:
            subprocess.Popen(["cmd", "/c", "start", "", "Sibelius"])
    else:
        target = str(resolved) if resolved else "sibelius"
        subprocess.Popen([target])


def open_score_file(file_path: str | Path, app_path: str | Path | None = None) -> None:
    """Open a score file (such as .sib, .mxl, .musicxml) in Sibelius."""
    resolved = find_sibelius_app(app_path)
    score_str = str(Path(file_path).expanduser().resolve())
    logger.info("Opening score %s in Sibelius (app: %s)...", score_str, resolved or app_path or "default")

    if sys.platform == "darwin":
        target = str(resolved) if resolved else "Sibelius"
        subprocess.Popen(["open", "-a", target, score_str])
    elif sys.platform == "win32":
        try:
            os.startfile(score_str)  # type: ignore[attr-defined]
        except AttributeError:
            target = str(resolved) if resolved else "Sibelius"
            subprocess.Popen([target, score_str])
    else:
        subprocess.Popen(["xdg-open", score_str])
