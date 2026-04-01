from pathlib import Path

import pytest

from reagent.security.trust import (
    AssetState,
    TrustEvent,
    TrustLevel,
    TrustStore,
    log_trust_event,
)


@pytest.fixture()
def trust_store(tmp_path: Path) -> TrustStore:
    store = TrustStore(tmp_path / "trust.jsonl")
    return store


class TestTrustLevel:
    def test_ordering(self) -> None:
        assert TrustLevel.UNTRUSTED < TrustLevel.REVIEWED
        assert TrustLevel.REVIEWED < TrustLevel.VERIFIED
        assert TrustLevel.VERIFIED < TrustLevel.NATIVE


class TestTrustStore:
    def test_get_or_create(self, trust_store: TrustStore) -> None:
        record = trust_store.get_or_create("test:skill:deploy")
        assert record.asset_id == "test:skill:deploy"
        assert record.trust_level == TrustLevel.UNTRUSTED

    def test_set_level(self, trust_store: TrustStore) -> None:
        record = trust_store.set_level(
            "test:skill:deploy", TrustLevel.REVIEWED, "abc123"
        )
        assert record.trust_level == TrustLevel.REVIEWED
        assert record.content_hash_at_review == "abc123"
        assert len(record.history) == 1

    def test_save_and_load(self, trust_store: TrustStore) -> None:
        trust_store.set_level("test:skill:deploy", TrustLevel.REVIEWED, "hash1")
        trust_store.set_level("test:agent:review", TrustLevel.VERIFIED, "hash2")
        trust_store.save()

        store2 = TrustStore(trust_store.path)
        store2.load()
        deploy = store2.get("test:skill:deploy")
        review = store2.get("test:agent:review")
        assert deploy is not None
        assert review is not None
        assert deploy.trust_level == TrustLevel.REVIEWED

    def test_all_records(self, trust_store: TrustStore) -> None:
        trust_store.set_level("b:skill:two", TrustLevel.UNTRUSTED)
        trust_store.set_level("a:skill:one", TrustLevel.REVIEWED)
        records = trust_store.all_records()
        assert len(records) == 2
        assert records[0].asset_id == "a:skill:one"

    def test_records_at_level(self, trust_store: TrustStore) -> None:
        trust_store.set_level("a:skill:one", TrustLevel.REVIEWED)
        trust_store.set_level("b:skill:two", TrustLevel.UNTRUSTED)
        reviewed = trust_store.records_at_level(TrustLevel.REVIEWED)
        assert len(reviewed) == 1
        assert reviewed[0].asset_id == "a:skill:one"


class TestPromotion:
    def test_promote_untrusted_to_reviewed(self, trust_store: TrustStore) -> None:
        trust_store.get_or_create("test:skill:a")
        record = trust_store.promote(
            "test:skill:a", TrustLevel.REVIEWED, "Passed review"
        )
        assert record.trust_level == TrustLevel.REVIEWED

    def test_promote_reviewed_to_verified(self, trust_store: TrustStore) -> None:
        trust_store.set_level("test:skill:a", TrustLevel.REVIEWED)
        record = trust_store.promote(
            "test:skill:a", TrustLevel.VERIFIED, "Fully trusted"
        )
        assert record.trust_level == TrustLevel.VERIFIED

    def test_cannot_skip_levels(self, trust_store: TrustStore) -> None:
        trust_store.get_or_create("test:skill:a")
        with pytest.raises(ValueError, match="Cannot promote"):
            trust_store.promote("test:skill:a", TrustLevel.VERIFIED, "Skip")

    def test_cannot_promote_to_native(self, trust_store: TrustStore) -> None:
        trust_store.set_level("test:skill:a", TrustLevel.VERIFIED)
        with pytest.raises(ValueError, match="NATIVE"):
            trust_store.promote("test:skill:a", TrustLevel.NATIVE, "Try native")

    def test_cannot_promote_suspended(self, trust_store: TrustStore) -> None:
        trust_store.set_level("test:skill:a", TrustLevel.REVIEWED)
        trust_store.suspend("test:skill:a", "Security issue")
        with pytest.raises(ValueError, match="suspended"):
            trust_store.promote("test:skill:a", TrustLevel.VERIFIED, "Try")


class TestDemotion:
    def test_demote_verified_to_reviewed(self, trust_store: TrustStore) -> None:
        trust_store.set_level("test:skill:a", TrustLevel.VERIFIED)
        record = trust_store.demote(
            "test:skill:a", TrustLevel.REVIEWED, "Integrity failure"
        )
        assert record.trust_level == TrustLevel.REVIEWED

    def test_demote_to_untrusted(self, trust_store: TrustStore) -> None:
        trust_store.set_level("test:skill:a", TrustLevel.REVIEWED)
        record = trust_store.demote("test:skill:a", TrustLevel.UNTRUSTED, "Suspicious")
        assert record.trust_level == TrustLevel.UNTRUSTED

    def test_cannot_demote_to_same_level(self, trust_store: TrustStore) -> None:
        trust_store.set_level("test:skill:a", TrustLevel.REVIEWED)
        with pytest.raises(ValueError, match="must be lower"):
            trust_store.demote("test:skill:a", TrustLevel.REVIEWED, "Same")

    def test_cannot_demote_to_higher(self, trust_store: TrustStore) -> None:
        trust_store.set_level("test:skill:a", TrustLevel.REVIEWED)
        with pytest.raises(ValueError, match="must be lower"):
            trust_store.demote("test:skill:a", TrustLevel.VERIFIED, "Higher")


class TestSuspend:
    def test_suspend(self, trust_store: TrustStore) -> None:
        trust_store.set_level("test:skill:a", TrustLevel.REVIEWED)
        record = trust_store.suspend("test:skill:a", "Compromised")
        assert record.state == AssetState.SUSPENDED

    def test_cannot_double_suspend(self, trust_store: TrustStore) -> None:
        trust_store.set_level("test:skill:a", TrustLevel.REVIEWED)
        trust_store.suspend("test:skill:a", "First time")
        with pytest.raises(ValueError, match="already suspended"):
            trust_store.suspend("test:skill:a", "Second time")

    def test_restore(self, trust_store: TrustStore) -> None:
        trust_store.set_level("test:skill:a", TrustLevel.REVIEWED)
        trust_store.suspend("test:skill:a", "Temp issue")
        record = trust_store.restore("test:skill:a", "Issue resolved")
        assert record.state == AssetState.ACTIVE

    def test_cannot_restore_active(self, trust_store: TrustStore) -> None:
        trust_store.set_level("test:skill:a", TrustLevel.REVIEWED)
        with pytest.raises(ValueError, match="not suspended"):
            trust_store.restore("test:skill:a", "Not suspended")


class TestTrustHistory:
    def test_history_tracks_all_changes(self, trust_store: TrustStore) -> None:
        trust_store.get_or_create("test:skill:a")
        trust_store.promote("test:skill:a", TrustLevel.REVIEWED, "Step 1")
        trust_store.promote("test:skill:a", TrustLevel.VERIFIED, "Step 2")
        trust_store.demote("test:skill:a", TrustLevel.UNTRUSTED, "Step 3")

        record = trust_store.get("test:skill:a")
        assert record is not None
        # 3 explicit changes, history should reflect all
        assert len(record.history) >= 3


class TestLogTrustEvent:
    def test_log_event(self, tmp_path: Path) -> None:
        log_path = tmp_path / "trust-log.jsonl"
        event = TrustEvent(
            asset_id="test:skill:a",
            action="promote",
            from_level=TrustLevel.UNTRUSTED,
            to_level=TrustLevel.REVIEWED,
            reason="Passed review",
        )
        log_trust_event(log_path, event)
        assert log_path.exists()
        lines = log_path.read_text().splitlines()
        assert len(lines) == 1
