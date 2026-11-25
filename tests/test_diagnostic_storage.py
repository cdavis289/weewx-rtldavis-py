"""Regression tests for bounded diagnostic storage."""

import os

from user.rtldavis_diagnostic_storage import (
    list_captures,
    prune_captures,
)


def capture(directory, kind, index, size=100):
    directory.mkdir(parents=True, exist_ok=True)

    if kind == "phase_c":
        name = "phase-c-20261124T120000Z-%032x.json" % index
    else:
        name = "gust-20261124T120000000000Z-%06d.json" % index

    path = directory / name
    path.write_bytes(b"x" * size)

    timestamp = 1700000000 + index
    os.utime(path, (timestamp, timestamp))

    return path


def test_file_count_retains_newest(tmp_path):
    files = [
        capture(tmp_path, "phase_c", i)
        for i in range(5)
    ]

    result = prune_captures([
        (tmp_path, "phase_c", 2),
    ])

    assert result["retained_files"] == 2
    assert result["removed_files"] == 3
    assert all(not path.exists() for path in files[:3])
    assert all(path.exists() for path in files[3:])


def test_byte_limit_retains_newest(tmp_path):
    files = [
        capture(tmp_path, "gust", i, size=100)
        for i in range(5)
    ]

    result = prune_captures([
        (tmp_path, "gust", 100),
    ], max_bytes=250)

    assert result["retained_bytes"] == 200
    assert result["removed_bytes"] == 300
    assert all(not path.exists() for path in files[:3])
    assert all(path.exists() for path in files[3:])


def test_combined_budget_across_directories(tmp_path):
    phase = tmp_path / "phase-c"
    gust = tmp_path / "gust"

    oldest = capture(phase, "phase_c", 1)
    middle = capture(gust, "gust", 2)
    newest = capture(phase, "phase_c", 3)

    result = prune_captures([
        (phase, "phase_c", 100),
        (gust, "gust", 100),
    ], max_bytes=200)

    assert not oldest.exists()
    assert middle.exists()
    assert newest.exists()
    assert result["retained_bytes"] == 200


def test_unrelated_files_are_preserved(tmp_path):
    owned = capture(tmp_path, "gust", 1)

    unrelated = [
        tmp_path / "notes.json",
        tmp_path / "gust-manual.json",
        tmp_path / "phase-c-backup.json",
        tmp_path / ".phase-c-test.tmp",
        tmp_path / "weather.db",
    ]

    for path in unrelated:
        path.write_text("preserve")

    prune_captures([
        (tmp_path, "gust", 0),
        (tmp_path, "phase_c", 0),
    ], max_bytes=0)

    assert not owned.exists()
    assert all(path.exists() for path in unrelated)


def test_symbolic_links_are_ignored(tmp_path):
    target = tmp_path / "important.json"
    target.write_text("preserve")

    link = tmp_path / "gust-20261124T120000000000Z-000001.json"
    link.symlink_to(target)

    result = prune_captures([
        (tmp_path, "gust", 0),
    ], max_bytes=0)

    assert link.is_symlink()
    assert target.read_text() == "preserve"
    assert result["removed_files"] == 0


def test_missing_directory_is_safe(tmp_path):
    directory = tmp_path / "missing"

    assert list_captures(directory, "phase_c") == []

    result = prune_captures([
        (directory, "phase_c", 100),
    ])

    assert result["retained_files"] == 0
    assert not directory.exists()


def test_oversized_capture_is_removed(tmp_path):
    path = capture(tmp_path, "phase_c", 1, size=500)

    result = prune_captures([
        (tmp_path, "phase_c", 100),
    ], max_bytes=200)

    assert not path.exists()
    assert result["retained_bytes"] == 0


def test_shared_directory_supports_both_types(tmp_path):
    phase = capture(tmp_path, "phase_c", 1)
    gust = capture(tmp_path, "gust", 2)

    result = prune_captures([
        (tmp_path, "phase_c", 100),
        (tmp_path, "gust", 100),
    ], max_bytes=100)

    assert not phase.exists()
    assert gust.exists()
    assert result["retained_files"] == 1


def test_cleanup_is_idempotent(tmp_path):
    capture(tmp_path, "phase_c", 1)
    capture(tmp_path, "phase_c", 2)

    groups = [(tmp_path, "phase_c", 1)]

    first = prune_captures(groups)
    second = prune_captures(groups)

    assert first["removed_files"] == 1
    assert second["removed_files"] == 0
    assert second["retained_files"] == 1
