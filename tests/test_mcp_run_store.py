from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.mcp.run_store import RunStore


def test_create_run_writes_meta(tmp_path: Path) -> None:
    store = RunStore(tmp_path)

    run_id = store.create_run()
    meta = store.load_meta(run_id)

    assert run_id.startswith("run-")
    assert meta["run_id"] == run_id
    assert "created_at" in meta


def test_save_and_load_stage_items(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    run_id = store.create_run("run-fixed")
    items = [{"title": "foo"}, {"title": "bar"}]

    path = store.save_items(run_id, "raw", items)
    loaded = store.load_items(run_id, "raw")

    assert path.name == "raw_items.json"
    assert loaded == items
    assert store.has_stage(run_id, "raw") is True


def test_update_meta_sets_updated_at(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    run_id = store.create_run("run-meta")

    meta = store.update_meta(run_id, {"status": "done"})

    assert meta["status"] == "done"
    assert "updated_at" in meta


def test_save_and_load_summary(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    run_id = store.create_run("run-summary")

    saved = store.save_summary(run_id, "zh", "# 摘要")
    content = store.load_summary(run_id, "zh")

    assert saved.name == "summary-zh.md"
    assert content == "# 摘要"


def test_unsupported_stage_raises(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    run_id = store.create_run("run-invalid-stage")

    with pytest.raises(ValueError, match="Unsupported stage"):
        store.save_items(run_id, "unknown", [])


def test_missing_run_raises(tmp_path: Path) -> None:
    store = RunStore(tmp_path)

    with pytest.raises(FileNotFoundError, match="Run not found"):
        store.run_dir("missing-run")


def test_rejects_path_traversal_run_id(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")

    with pytest.raises(ValueError, match="Invalid run_id"):
        store.create_run("../outside")

    assert not (tmp_path / "outside").exists()


def test_rejects_unsafe_summary_language(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    run_id = store.create_run("run-summary-safe")

    with pytest.raises(ValueError, match="Invalid summary language"):
        store.save_summary(run_id, "../zh", "# unsafe")


def test_missing_artifact_raises(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    run_id = store.create_run("run-missing-file")

    with pytest.raises(FileNotFoundError, match="Artifact not found"):
        store.read_json(run_id, "does-not-exist.json")


def test_list_runs_returns_desc_order(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    run1 = store.create_run("run-1")
    store.update_meta(run1, {"seq": 1})
    run2 = store.create_run("run-2")
    store.update_meta(run2, {"seq": 2})

    runs = store.list_runs(limit=10)

    assert runs[0]["run_id"] == "run-2"
    assert runs[1]["run_id"] == "run-1"


def test_cleanup_old_runs_deletes_runs_older_than_retention(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    old_run = store.create_run("run-old")
    recent_run = store.create_run("run-recent")
    store.update_meta(old_run, {"created_at": "2026-05-01T00:00:00+00:00"})
    store.update_meta(recent_run, {"created_at": "2026-07-01T00:00:00+00:00"})

    deleted = store.cleanup_old_runs(
        retention_days=30,
        now=datetime(2026, 7, 5, tzinfo=timezone.utc),
    )

    assert deleted == 1
    assert not (tmp_path / "run-old").exists()
    assert (tmp_path / "run-recent").exists()
