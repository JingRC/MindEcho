"""Regression: preserve-timeline retake must NOT inflate total duration.

This locks the behavior that during selection retake (preserve timeline),
progress callbacks must keep `recording_duration` frozen at baseline.

Run:
  python -u regression_tests\validate_retake_preserve_duration_freeze.py
"""

import os
import sys


def test_preserve_timeline_freezes_duration():
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    SRC = os.path.join(ROOT, 'src')
    if SRC not in sys.path:
        sys.path.insert(0, SRC)

    from gui.integrated_recording_interface import IntegratedRecordingInterface

    class Dummy:
        def __init__(self):
            self._retake_active_range = (10.0, 15.0)
            self._retake_preserved_recording_duration = 30.0
            self.recording_duration = 30.0
            self.current_duration = 30.0
            self.current_global_time = 10.0
            self.is_paused = False
            self._backing_paused = False
            self._retake_overlay_virtual_time = 12.5

        def _retake_overlay_active(self):
            return True

        def _retake_should_preserve_timeline(self):
            return True

        def get_effective_recording_time(self, raw):
            return raw

        def _enforce_active_retake_bounds(self, guard_time, source="progress"):
            # store last call for assertions
            self._last_guard = (float(guard_time), str(source))

    dummy = Dummy()

    # Simulate progress jumping forward (e.g., wall-clock keeps running)
    IntegratedRecordingInterface.on_recording_progress(dummy, 35.0)

    assert abs(dummy.recording_duration - 30.0) < 1e-6, f"recording_duration inflated: {dummy.recording_duration}"
    assert abs(dummy.current_duration - 30.0) < 1e-6, f"current_duration inflated: {dummy.current_duration}"

    # Guard should prefer virtual time during retake
    gt, src = getattr(dummy, "_last_guard", (None, None))
    assert gt is not None and abs(gt - 12.5) < 1e-6, f"guard_time should follow virtual retake clock, got {gt}"
    assert src == "virtual", f"guard_source should be virtual during preserve retake, got {src}"


if __name__ == "__main__":
    test_preserve_timeline_freezes_duration()
    print("OK: validate_retake_preserve_duration_freeze passed")
