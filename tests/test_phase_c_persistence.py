"""Phase C Step 6B persistence and installation safety tests."""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bin'))
from user.rtldavis_phase_c_diagnostics import PhaseCDiagnostics, persist_captures


def completed():
    recorder = PhaseCDiagnostics(before_seconds=1, after_seconds=1, clock=lambda: 10)
    recorder.observe('before', timestamp=10)
    recorder.trigger('failure', timestamp=10)
    return recorder


def test_success_acknowledges_and_writes_json(tmp_path):
    recorder = completed()
    paths = persist_captures(recorder, tmp_path, timestamp=12)
    assert len(paths) == 1
    assert json.loads(paths[0].read_text())['reason'] == 'failure'
    assert recorder.peek_pending(timestamp=12) is None
    assert persist_captures(recorder, tmp_path, timestamp=12) == []


def test_failed_write_keeps_capture_and_retry_succeeds(tmp_path):
    recorder = completed()
    with patch('os.replace', side_effect=OSError('disk failure')):
        with pytest.raises(OSError, match='disk failure'):
            persist_captures(recorder, tmp_path, timestamp=12)
    assert recorder.peek_pending(timestamp=12) is not None
    assert list(tmp_path.iterdir()) == []
    assert len(persist_captures(recorder, tmp_path, timestamp=12)) == 1


def test_retention_only_deletes_phase_c_files(tmp_path):
    unrelated = tmp_path / 'other.json'
    unrelated.write_text('keep')
    recorder = completed()
    first = persist_captures(recorder, tmp_path, timestamp=12, max_files=1)[0]
    second_recorder = completed()
    second = persist_captures(second_recorder, tmp_path, timestamp=12, max_files=1)[0]
    assert second.exists()
    assert not first.exists()
    assert unrelated.read_text() == 'keep'


def test_pending_queue_remains_bounded_on_failure():
    recorder = PhaseCDiagnostics(before_seconds=0, after_seconds=0,
                                 max_pending=2, clock=lambda: 10)
    for index in range(3):
        recorder.trigger(str(index), timestamp=10 + index)
        recorder.peek_pending(timestamp=10 + index)
    assert recorder.dropped_captures == 1
    assert [item['reason'] for item in recorder.drain(timestamp=20)] == ['1', '2']


def test_installer_includes_phase_c_module():
    assert "'bin/user/rtldavis_phase_c_diagnostics.py'" in (ROOT / 'install.py').read_text()
