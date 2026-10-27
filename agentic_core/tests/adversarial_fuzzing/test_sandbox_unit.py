"""Unit tests for the path guard (RP-16, section 1).

Design tests only. The 50-vector evaluation suite is a separate file (Epic 4).
"""

import logging

import pytest

from agentic_core.mcp_servers.filesystem_server.sandbox import (
    SandboxConfig,
    SandboxViolation,
    check_path,
)


@pytest.fixture()
def config(tmp_path):
    vault = tmp_path / "vault"
    for name in ("Inbox", "Meetings", "Ideas"):
        (vault / name).mkdir(parents=True)
    return SandboxConfig(vault_root=vault)


@pytest.mark.parametrize(
    "path",
    ["Inbox/a.md", "Meetings/2026-10-18_standup.md", "Ideas/deep/folder/idea.md"],
)
def test_good_paths_are_allowed(config, path):
    result = check_path(config, path)
    assert result.is_relative_to(config.vault_root.resolve())
    assert result.name.endswith(".md")


@pytest.mark.parametrize(
    "path, reason",
    [
        ("../../etc/passwd", "TRAVERSAL"),
        ("Inbox/../../x.md", "TRAVERSAL"),
        ("Inbox\\..\\..\\x.md", "TRAVERSAL"),
        ("/etc/passwd.md", "ABSOLUTE"),
        ("\\\\server\\share\\x.md", "ABSOLUTE"),
        ("C:\\Windows\\x.md", "DRIVE_OR_STREAM"),
        ("Inbox/a.md:stream", "DRIVE_OR_STREAM"),
        ("Inbox/a.md\x00.txt", "NULL_BYTE"),
        ("Inbox/a\nb.md", "CONTROL_CHAR"),
        ("", "EMPTY"),
        ("   ", "EMPTY"),
        ("Inbox//a.md", "EMPTY_COMPONENT"),
        ("x.md", "NOT_ALLOWED_DIR"),
        ("Other/a.md", "NOT_ALLOWED_DIR"),
        ("inbox/a.md", "NOT_ALLOWED_DIR"),
        ("Inbox/a.py", "BAD_SUFFIX"),
        ("Inbox/NUL.md", "RESERVED_NAME"),
        ("Inbox/a.md.", "BAD_COMPONENT"),
        ("Inbox/" + "a" * 300 + ".md", "TOO_LONG"),
        (None, "NOT_TEXT"),
        (123, "NOT_TEXT"),
    ],
)
def test_bad_paths_are_blocked(config, path, reason):
    with pytest.raises(SandboxViolation) as info:
        check_path(config, path)
    assert info.value.reason == reason
    assert str(info.value) == reason  # the error never carries the path


def test_symlink_inside_zone_pointing_out_is_blocked(config, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (config.vault_root / "Ideas" / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("cannot create symlinks here (Windows needs Developer Mode)")
    with pytest.raises(SandboxViolation) as info:
        check_path(config, "Ideas/link/x.md")
    assert info.value.reason == "OUTSIDE_ZONE"


def test_allowed_folder_that_is_a_symlink_out_is_blocked(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (vault / "Inbox").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("cannot create symlinks here (Windows needs Developer Mode)")
    with pytest.raises(SandboxViolation) as info:
        check_path(SandboxConfig(vault_root=vault), "Inbox/x.md")
    assert info.value.reason == "OUTSIDE_VAULT"


def test_every_violation_is_logged(config, caplog):
    with caplog.at_level(logging.WARNING, logger="agentic_core.sandbox"):
        with pytest.raises(SandboxViolation):
            check_path(config, "../../etc/passwd")
    assert "reason=TRAVERSAL" in caplog.text