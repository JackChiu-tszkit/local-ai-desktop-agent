from pathlib import Path

import pytest

from app.security.permissions import PathGuard, default_protected_prefixes, is_drive_root, is_secret_path


def test_rejects_relative_and_parent_escape(workspace):
    guard = PathGuard(list(workspace.values()), [])
    with pytest.raises(PermissionError):
        guard.resolve("invoice.pdf", workspace)
    with pytest.raises(PermissionError):
        guard.resolve("downloads/../outside.txt", workspace)


def test_rejects_path_outside_roots(tmp_path, workspace):
    guard = PathGuard(list(workspace.values()), [])
    outside = tmp_path.parent / "outside.txt"
    with pytest.raises(PermissionError):
        guard.resolve(str(outside), workspace)


def test_rejects_windows_directory():
    guard = PathGuard([Path("C:/")], default_protected_prefixes())
    with pytest.raises(PermissionError):
        guard.resolve(r"C:\Windows\System32\notepad.exe")


def test_logical_folder_stays_inside_root(workspace):
    guard = PathGuard(list(workspace.values()), default_protected_prefixes())
    resolved = guard.resolve("documents/notes.txt", workspace)
    assert resolved.parent == workspace["documents"]


def test_secret_names_are_detected():
    assert is_secret_path(".env")
    assert is_secret_path("id_rsa")
    assert is_secret_path("archive.pem")
    assert not is_secret_path("invoice_2025.pdf")


def test_drive_root_detected(tmp_path):
    assert is_drive_root(Path("C:/"))
    assert not is_drive_root(tmp_path)
