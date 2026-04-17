from pathlib import Path

import pytest

from agentguard.security.trust import (
    AssetState,
    TrustEvent,
    TrustLevel,
    TrustStore,
    log_trust_event,
)

_U = TrustLevel.UNTRUSTED
_R = TrustLevel.REVIEWED
_V = TrustLevel.VERIFIED
_N = TrustLevel.NATIVE


@pytest.fixture()
def trust_store(tmp_path: Path) -> TrustStore:
    store = TrustStore(tmp_path / "trust.jsonl")
    return store


class TestTrustLevel:
    def test_ordering(self) -> None:
        assert _U < _R
        assert _R < _V
        assert _V < _N


class TestTrustStore:
    def test_get_or_create(self, trust_store: TrustStore) -> None:
        record = trust_store.get_or_create("test:skill:deploy")
        assert record.asset_id == "test:skill:deploy"
        assert record.trust_level == _U

    def test_set_level(self, trust_store: TrustStore) -> None:
        record = trust_store.set_level("test:skill:deploy", _R, "abc123")
        assert record.trust_level == _R
        assert record.content_hash_at_review == "abc123"
        assert len(record.history) == 1

    def test_save_and_load(self, trust_store: TrustStore) -> None:
        trust_store.set_level("test:skill:deploy", _R, "hash1")
        trust_store.set_level("test:agent:review", _V, "hash2")
        trust_store.save()

        store2 = TrustStore(trust_store.path)
        store2.load()
        deploy = store2.get("test:skill:deploy")
        review = store2.get("test:agent:review")
        assert deploy is not None
        assert review is not None
        assert deploy.trust_level == _R

    def test_all_records(self, trust_store: TrustStore) -> None:
        trust_store.set_level("b:skill:two", _U)
        trust_store.set_level("a:skill:one", _R)
        records = trust_store.all_records()
        assert len(records) == 2
        assert records[0].asset_id == "a:skill:one"

    def test_records_at_level(self, trust_store: TrustStore) -> None:
        trust_store.set_level("a:skill:one", _R)
        trust_store.set_level("b:skill:two", _U)
        reviewed = trust_store.records_at_level(_R)
        assert len(reviewed) == 1
        assert reviewed[0].asset_id == "a:skill:one"


class TestPromotion:
    @pytest.mark.parametrize(
        ("initial_level", "target_level"),
        [
            pytest.param(None, _R, id="untrusted_to_reviewed"),
            pytest.param(_R, _V, id="reviewed_to_verified"),
        ],
    )
    def test_promote_valid(
        self,
        trust_store: TrustStore,
        initial_level: TrustLevel | None,
        target_level: TrustLevel,
    ) -> None:
        if initial_level is None:
            trust_store.get_or_create("test:skill:a")
        else:
            trust_store.set_level("test:skill:a", initial_level)
        record = trust_store.promote("test:skill:a", target_level, "ok")
        assert record.trust_level == target_level

    @pytest.mark.parametrize(
        ("initial_level", "suspend_first", "target_level", "match"),
        [
            pytest.param(None, False, _V, "Cannot promote", id="skip"),
            pytest.param(_V, False, _N, "NATIVE", id="to_native"),
            pytest.param(_R, True, _V, "suspended", id="suspended"),
        ],
    )
    def test_promote_invalid(
        self,
        trust_store: TrustStore,
        initial_level: TrustLevel | None,
        suspend_first: bool,
        target_level: TrustLevel,
        match: str,
    ) -> None:
        if initial_level is None:
            trust_store.get_or_create("test:skill:a")
        else:
            trust_store.set_level("test:skill:a", initial_level)
        if suspend_first:
            trust_store.suspend("test:skill:a", "Security issue")
        with pytest.raises(ValueError, match=match):
            trust_store.promote("test:skill:a", target_level, "Try")


class TestDemotion:
    @pytest.mark.parametrize(
        ("initial_level", "target_level", "reason"),
        [
            pytest.param(_V, _R, "Integrity failure", id="v_to_r"),
            pytest.param(_R, _U, "Suspicious", id="r_to_u"),
        ],
    )
    def test_demote_valid(
        self,
        trust_store: TrustStore,
        initial_level: TrustLevel,
        target_level: TrustLevel,
        reason: str,
    ) -> None:
        trust_store.set_level("test:skill:a", initial_level)
        record = trust_store.demote("test:skill:a", target_level, reason)
        assert record.trust_level == target_level

    @pytest.mark.parametrize(
        ("initial_level", "target_level"),
        [
            pytest.param(_R, _R, id="same_level"),
            pytest.param(_R, _V, id="higher_level"),
        ],
    )
    def test_demote_invalid(
        self,
        trust_store: TrustStore,
        initial_level: TrustLevel,
        target_level: TrustLevel,
    ) -> None:
        trust_store.set_level("test:skill:a", initial_level)
        with pytest.raises(ValueError, match="must be lower"):
            trust_store.demote("test:skill:a", target_level, "Bad")


class TestSuspend:
    def test_suspend(self, trust_store: TrustStore) -> None:
        trust_store.set_level("test:skill:a", _R)
        record = trust_store.suspend("test:skill:a", "Compromised")
        assert record.state == AssetState.SUSPENDED

    def test_cannot_double_suspend(self, trust_store: TrustStore) -> None:
        trust_store.set_level("test:skill:a", _R)
        trust_store.suspend("test:skill:a", "First time")
        with pytest.raises(ValueError, match="already suspended"):
            trust_store.suspend("test:skill:a", "Second time")

    def test_restore(self, trust_store: TrustStore) -> None:
        trust_store.set_level("test:skill:a", _R)
        trust_store.suspend("test:skill:a", "Temp issue")
        record = trust_store.restore("test:skill:a", "Issue resolved")
        assert record.state == AssetState.ACTIVE

    def test_cannot_restore_active(self, trust_store: TrustStore) -> None:
        trust_store.set_level("test:skill:a", _R)
        with pytest.raises(ValueError, match="not suspended"):
            trust_store.restore("test:skill:a", "Not suspended")


class TestTrustHistory:
    def test_history_tracks_all_changes(self, trust_store: TrustStore) -> None:
        trust_store.get_or_create("test:skill:a")
        trust_store.promote("test:skill:a", _R, "Step 1")
        trust_store.promote("test:skill:a", _V, "Step 2")
        trust_store.demote("test:skill:a", _U, "Step 3")

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
            from_level=_U,
            to_level=_R,
            reason="Passed review",
        )
        log_trust_event(log_path, event)
        assert log_path.exists()
        lines = log_path.read_text().splitlines()
        assert len(lines) == 1
