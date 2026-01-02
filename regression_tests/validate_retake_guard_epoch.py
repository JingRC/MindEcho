import os, sys, time

# Keep imports lightweight; we do NOT instantiate Qt widgets here.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from gui.integrated_recording_interface import ECGStylePitchVisualizer


class _DummyPitchStore:
    def append_point(self, *args, **kwargs):
        return None

    def last_time(self):
        return 0.0


class DummySelf:
    """Minimal stand-in to exercise ECGStylePitchVisualizer.add_pitch_data guard logic.

    Regression target:
    - When retake guard is active and the incoming packet lacks `_epoch`,
      we must NOT drop the packet during retake-live conditions.
    """

    def __init__(self):
        now = time.time()
        self.debug_flags = {}

        # Match real accompaniment/analyzing paths: some early epoch filters
        # allow missing _epoch only in analyzing/backing modes.
        self.is_analyzing = True
        self.backing_mode = 'accompaniment'

        # Force guard to be active and not expired.
        self._retake_block_range = (10.0, 15.0)
        self._retake_epoch_guard_epoch = 123
        self._retake_epoch_guard_until = now + 60.0
        self._retake_guard_active = False

        # Ensure we're not in countdown freeze mode.
        self._retake_countdown_active = False
        self._retake_countdown_block_add = False

        # Avoid unrelated early returns.
        self._cleanup_block_add = False
        self._retake_dual_mode_active = False
        self._retake_drop_until_timestamp = 0.0
        self._time_offset_shift = 0.0

        # Time base (won't be used if pitch_data provides global_time).
        self.start_time = now
        self._total_paused_time = 0.0

        # Retake flags kept false so we specifically exercise the guard-as-retake-live path.
        self._retake_overlay_preview_active = False
        self.retake_selection_active = False

        # Disable follow/scroll logic to keep dummy minimal.
        self.auto_follow = False
        self.auto_scroll_enabled = False
        self.center_display_time = 8.0
        self.time_window = 16.0
        self.max_history_time = 0.0

        # Epoch baseline
        self._current_epoch = 123

        # Minimal containers used later in add_pitch_data
        self._pitch_store = _DummyPitchStore()
        self.time_data = []
        self.pitch_data = [0.0]
        self.confidence_data = []
        self.note_data = []

    # Methods referenced by add_pitch_data; keep them safe.
    def _retake_snapshot_active(self):
        return False

    def _get_active_retake_range(self):
        return (10.0, 15.0)

    def update_display(self):
        return None

    def _instant_refresh(self):
        return None

    def update_guides(self):
        return None

    def __getattr__(self, name):
        # Provide conservative defaults for any attribute not stubbed.
        # This keeps the regression focused on guard/epoch behavior.
        if name in ('ax', 'canvas', 'pitch_line', '_segment_points', '_batched_points'):
            return None
        # Timers/windows/objects default to None
        if name.endswith('_timer') or name.endswith('_win'):
            return None
        # Numeric/boolean defaults
        return 0.0


def assert_true(cond, msg):
    if not cond:
        raise AssertionError(msg)


def main():
    dummy = DummySelf()

    pkt = {
        'timestamp': time.time(),
        'global_time': 12.0,  # inside guard range
        'frequency': 440.0,
        'confidence': 0.95,
        'has_pitch': True,
        'note_info': {'midi': 69.0},
        # IMPORTANT: no '_epoch'
    }

    # Call the real production method against our dummy self.
    ECGStylePitchVisualizer.add_pitch_data(dummy, pkt)

    # Guard regression: we should have injected/normalized the epoch rather than dropping.
    assert_true('_epoch' in pkt, 'retake-guard: missing _epoch packet should be normalized, not dropped')
    assert_true(int(pkt.get('_epoch')) == 123, 'retake-guard: injected _epoch should match guard/current epoch')

    dropped = int(getattr(dummy, '_retake_missing_epoch_dropped', 0) or 0)
    assert_true(dropped == 0, f'retake-guard: should not increment missing-epoch drop counter, got {dropped}')

    print('OK: validate_retake_guard_epoch passed')


if __name__ == '__main__':
    main()
