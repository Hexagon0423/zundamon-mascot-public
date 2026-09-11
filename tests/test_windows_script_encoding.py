"""Encoding rules for the scripts Windows runs directly.

Both Windows Script Host (.vbs) and Windows PowerShell 5.1 (.ps1) read a file
without a byte-order mark in the ANSI code page -- CP932 on this machine. A
UTF-8 Japanese comment then decodes into garbage, and worse, a character whose
last byte is a CP932 lead byte (「。」 ends in 0x82) swallows the newline after
it, silently commenting out the next line of code.

That is how the login script that starts VOICEVOX died on 2026-09-11: its
`Set sh = ...` line was eaten by the comment above it, and the only symptom was
a WSH dialog on login and a mascot with no voice. Nothing about the file looks
wrong in an editor, which is why this is a test and not a note.
"""

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SEARCHED = ("scripts", "dotfiles")
BOM = b"\xef\xbb\xbf"


def _files(pattern: str) -> list[Path]:
    return sorted(p for root in SEARCHED for p in (REPO / root).rglob(pattern))


def _has_non_ascii(data: bytes) -> bool:
    return any(b > 0x7F for b in data)


@pytest.mark.parametrize("path", _files("*.vbs"), ids=lambda p: p.name)
def test_vbs_files_are_plain_ascii(path):
    """WSH has no reliable way to be told a .vbs is UTF-8, so keep them ASCII."""
    assert not _has_non_ascii(path.read_bytes()), f"{path.name} に非ASCII文字があるのだ"


@pytest.mark.parametrize("path", _files("*.ps1"), ids=lambda p: p.name)
def test_ps1_files_with_non_ascii_carry_a_bom(path):
    data = path.read_bytes()
    if _has_non_ascii(data):
        assert data.startswith(BOM), f"{path.name} は日本語を含むのにBOMが無いのだ"


def test_the_search_actually_finds_the_login_scripts():
    """Guards the guard: a moved directory would make the tests above pass vacuously."""
    names = {p.name for p in _files("*.vbs")} | {p.name for p in _files("*.ps1")}
    assert "start_voicevox_minimized.vbs" in names
    assert "start_voicevox_minimized.ps1" in names
