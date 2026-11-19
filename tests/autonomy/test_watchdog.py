"""Watchdog 单测：连续相同失败签名 → trip，签名变化 → 重置。"""

import json

from yuleosh.pipeline.autonomy import watchdog as wd
from yuleosh.pipeline.autonomy.watchdog import (
    ProgressRecord,
    Watchdog,
    artifact_digest,
    findings_signature,
    get_watchdog,
)


def test_same_signature_trips_at_threshold(tmp_path):
    dog = Watchdog(session_dir=tmp_path, max_stalls=3)
    assert dog.record("arch-review", signature="same").tripped is False
    assert dog.record("arch-review", signature="same").streak == 2
    rec = dog.record("arch-review", signature="same")
    assert rec.streak == 3
    assert rec.tripped is True
    assert dog.tripped is True


def test_signature_change_resets_streak(tmp_path):
    dog = Watchdog(session_dir=tmp_path, max_stalls=2)
    dog.record("arch-review", signature="a")
    assert dog.record("arch-review", signature="b").streak == 1
    assert dog.record("arch-review", signature="b").tripped is True


def test_artifact_digest_used_when_no_signature(tmp_path):
    artifact = tmp_path / "r.json"
    artifact.write_text('{"status": "retry"}', encoding="utf-8")
    digest = artifact_digest(artifact)
    assert digest
    dog = Watchdog(session_dir=tmp_path, max_stalls=2)
    dog.record("r", signature="", artifact_digest_value=digest)
    assert dog.record("r", signature="", artifact_digest_value=digest).tripped


def test_progress_when_digest_changes(tmp_path):
    dog = Watchdog(session_dir=tmp_path, max_stalls=2)
    dog.record("r", signature="", artifact_digest_value="d1")
    rec = dog.record("r", signature="", artifact_digest_value="d2")
    assert rec.streak == 1 and rec.tripped is False


def test_state_persisted_and_reloaded(tmp_path):
    dog = Watchdog(session_dir=tmp_path, max_stalls=3)
    dog.record("development", signature="sig", status="retry")
    state = json.loads((tmp_path / "watchdog.json").read_text(encoding="utf-8"))
    assert state["records"]["development"]["signature"] == "sig"

    reloaded = Watchdog(session_dir=tmp_path, max_stalls=3)
    rec = reloaded.record("development", signature="sig")
    assert rec.streak == 2


def test_findings_signature_order_independent():
    a = [{"rule": "R1", "message": "m1", "file": "f.c"},
         {"rule": "R2", "message": "m2", "file": "g.c"}]
    assert findings_signature(a) == findings_signature(list(reversed(a)))
    assert findings_signature([]) == ""
    assert findings_signature(a) != findings_signature(a[:1])


def test_get_watchdog_caches_on_session(tmp_path):
    class _Session:
        session_dir = str(tmp_path)

    session = _Session()
    first = get_watchdog(session)
    second = get_watchdog(session)
    assert isinstance(first, Watchdog)
    assert first is second


def test_record_dataclass_roundtrip():
    rec = ProgressRecord(step="s", signature="x")
    assert rec.to_dict()["step"] == "s"
    assert wd.DEFAULT_MAX_STALLS == 3
