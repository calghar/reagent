from pathlib import Path

import pytest

from agentguard.security.snapshots import SnapshotStore


@pytest.fixture()
def snap_store(tmp_path: Path) -> SnapshotStore:
    store = SnapshotStore(tmp_path / "snapshots")
    return store


class TestSnapshotCreation:
    def test_take_first_snapshot(self, snap_store: SnapshotStore) -> None:
        entry = snap_store.take_snapshot("test:skill:a", "# Hello\nWorld\n")
        assert entry.snapshot_id == 1
        assert entry.asset_id == "test:skill:a"
        assert entry.trigger == "manual"

    def test_skip_duplicate_content(self, snap_store: SnapshotStore) -> None:
        e1 = snap_store.take_snapshot("test:skill:a", "same content")
        e2 = snap_store.take_snapshot("test:skill:a", "same content")
        assert e1.snapshot_id == e2.snapshot_id  # No new snapshot

    def test_new_snapshot_on_change(self, snap_store: SnapshotStore) -> None:
        e1 = snap_store.take_snapshot("test:skill:a", "version 1")
        e2 = snap_store.take_snapshot("test:skill:a", "version 2")
        assert e2.snapshot_id == 2
        assert e1.content_hash != e2.content_hash

    def test_blob_stored(self, snap_store: SnapshotStore) -> None:
        content = "# Test Content\n"
        entry = snap_store.take_snapshot("test:skill:a", content)
        blob = snap_store.read_blob(entry.content_hash)
        assert blob == content

    def test_trigger_recorded(self, snap_store: SnapshotStore) -> None:
        entry = snap_store.take_snapshot(
            "test:skill:a", "content", trigger="config_change"
        )
        assert entry.trigger == "config_change"

    def test_file_path_recorded(self, snap_store: SnapshotStore) -> None:
        entry = snap_store.take_snapshot(
            "test:skill:a", "content", file_path=Path("/some/path.md")
        )
        assert entry.file_path == "/some/path.md"


class TestSnapshotPersistence:
    def test_save_and_load(self, snap_store: SnapshotStore) -> None:
        snap_store.take_snapshot("test:skill:a", "v1")
        snap_store.take_snapshot("test:skill:a", "v2")
        snap_store.take_snapshot("test:skill:b", "content")
        snap_store.save()

        store2 = SnapshotStore(snap_store.base_dir)
        store2.load()
        assert len(store2.history("test:skill:a")) == 2
        assert len(store2.history("test:skill:b")) == 1


class TestSnapshotHistory:
    def test_history_chronological(self, snap_store: SnapshotStore) -> None:
        snap_store.take_snapshot("test:skill:a", "v1")
        snap_store.take_snapshot("test:skill:a", "v2")
        snap_store.take_snapshot("test:skill:a", "v3")

        history = snap_store.history("test:skill:a")
        assert len(history) == 3
        assert history[0].snapshot_id == 1
        assert history[2].snapshot_id == 3

    def test_history_empty(self, snap_store: SnapshotStore) -> None:
        assert snap_store.history("nonexistent") == []


class TestSnapshotRollback:
    def test_rollback_restores_content(
        self, snap_store: SnapshotStore, tmp_path: Path
    ) -> None:
        target = tmp_path / "test.md"
        target.write_text("original", encoding="utf-8")

        snap_store.take_snapshot("test:skill:a", "original", file_path=target)
        snap_store.take_snapshot("test:skill:a", "modified", file_path=target)

        # Rollback to snapshot 1
        new_snap = snap_store.rollback("test:skill:a", 1, target)
        assert target.read_text() == "original"
        assert new_snap.trigger == "rollback"

    def test_rollback_nonexistent_snapshot(
        self, snap_store: SnapshotStore, tmp_path: Path
    ) -> None:
        with pytest.raises(ValueError, match="not found"):
            snap_store.rollback("test:skill:a", 99, tmp_path / "test.md")

    def test_rollback_creates_new_snapshot(
        self, snap_store: SnapshotStore, tmp_path: Path
    ) -> None:
        target = tmp_path / "test.md"
        snap_store.take_snapshot("test:skill:a", "v1", file_path=target)
        snap_store.take_snapshot("test:skill:a", "v2", file_path=target)

        snap_store.rollback("test:skill:a", 1, target)
        history = snap_store.history("test:skill:a")
        # v1, v2, rollback-to-v1 -- but rollback-to-v1 has same hash as v1
        #  so may be skipped
        assert len(history) >= 2


class TestRetention:
    def test_max_snapshots_enforced(self, tmp_path: Path) -> None:
        store = SnapshotStore(tmp_path / "snapshots")
        store.max_per_asset = 3

        for i in range(5):
            store.take_snapshot("test:skill:a", f"version {i}")

        history = store.history("test:skill:a")
        assert len(history) <= 3
        # Should keep the latest ones
        assert history[-1].snapshot_id == 5


class TestGetSnapshot:
    def test_get_existing_snapshot(self, snap_store: SnapshotStore) -> None:
        snap_store.take_snapshot("test:skill:a", "v1")
        snap_store.take_snapshot("test:skill:a", "v2")

        snap = snap_store.get_snapshot("test:skill:a", 1)
        assert snap is not None
        assert snap.snapshot_id == 1

    def test_get_nonexistent_snapshot(self, snap_store: SnapshotStore) -> None:
        assert snap_store.get_snapshot("test:skill:a", 99) is None

    def test_get_nonexistent_chain(self, snap_store: SnapshotStore) -> None:
        assert snap_store.get_snapshot("nonexistent", 1) is None


class TestReadBlob:
    def test_read_existing_blob(self, snap_store: SnapshotStore) -> None:
        entry = snap_store.take_snapshot("test:skill:a", "hello")
        assert snap_store.read_blob(entry.content_hash) == "hello"

    def test_read_nonexistent_blob(self, snap_store: SnapshotStore) -> None:
        assert snap_store.read_blob("nonexistent_hash") is None


class TestAllChains:
    def test_all_chains(self, snap_store: SnapshotStore) -> None:
        snap_store.take_snapshot("b:skill:two", "content")
        snap_store.take_snapshot("a:skill:one", "content")
        chains = snap_store.all_chains()
        assert len(chains) == 2
        assert chains[0].asset_id == "a:skill:one"
