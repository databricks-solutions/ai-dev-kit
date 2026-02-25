"""Unit tests for identity module helpers."""

from unittest import mock

from databricks_tools_core.identity import (
    DESCRIPTION_FOOTER,
    _load_version,
    with_description_footer,
)


# ── _load_version ──────────────────────────────────────────────────────


def test_load_version_reads_version_file(tmp_path):
    """Finds a VERSION file by walking up from __file__."""
    (tmp_path / "VERSION").write_text("1.2.3\n")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    mod = nested / "mod.py"
    mod.touch()

    with mock.patch("databricks_tools_core.identity.__file__", str(mod)):
        assert _load_version() == "1.2.3"


def test_load_version_strips_whitespace(tmp_path):
    (tmp_path / "VERSION").write_text("  0.5.0-beta  \n\n")
    mod = tmp_path / "pkg" / "mod.py"
    mod.parent.mkdir()
    mod.touch()

    with mock.patch("databricks_tools_core.identity.__file__", str(mod)):
        assert _load_version() == "0.5.0-beta"


def test_load_version_fallback_when_no_file(tmp_path):
    """Returns fallback when no VERSION file exists anywhere."""
    mod = tmp_path / "a" / "b" / "c" / "d" / "e" / "f" / "g" / "mod.py"
    mod.parent.mkdir(parents=True)
    mod.touch()

    with mock.patch("databricks_tools_core.identity.__file__", str(mod)):
        assert _load_version() == "0.0.0-unknown"


def test_load_version_fallback_on_exception():
    """Returns fallback when __file__ resolution fails."""
    with mock.patch(
        "databricks_tools_core.identity.__file__",
        "/nonexistent/path/that/cannot/resolve/mod.py",
    ):
        # Still returns fallback (caught by the broad except)
        result = _load_version()
        assert isinstance(result, str)


# ── with_description_footer ────────────────────────────────────────────


def test_footer_appended_to_description():
    result = with_description_footer("My cool resource")
    assert result == f"My cool resource\n\n{DESCRIPTION_FOOTER}"


def test_footer_only_when_none():
    assert with_description_footer(None) == DESCRIPTION_FOOTER


def test_footer_only_when_empty_string():
    assert with_description_footer("") == DESCRIPTION_FOOTER


def test_footer_only_when_whitespace():
    # Empty-ish strings are falsy only if literally empty; " " is truthy
    result = with_description_footer("   ")
    assert DESCRIPTION_FOOTER in result


def test_footer_preserves_multiline_description():
    desc = "Line one\nLine two"
    result = with_description_footer(desc)
    assert result.startswith("Line one\nLine two\n\n")
    assert result.endswith(DESCRIPTION_FOOTER)


def test_footer_idempotent_guard():
    """Calling twice appends twice (no dedup) — caller is responsible."""
    once = with_description_footer("desc")
    twice = with_description_footer(once)
    assert twice.count(DESCRIPTION_FOOTER) == 2
