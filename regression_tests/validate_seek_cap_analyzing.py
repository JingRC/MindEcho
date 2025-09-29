import os, sys, time
import math
import traceback

# Use non-interactive backend for matplotlib if present
try:
    import matplotlib
    matplotlib.use('Agg')
except Exception:
    pass

# Ensure we can import from src
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)

# Minimal Qt stub runner (prefer qtpy for backend-agnostic imports)
try:
    from qtpy import QtWidgets
except Exception:
    try:
        from PyQt5 import QtWidgets  # type: ignore
    except Exception:
        from PyQt6 import QtWidgets  # type: ignore

# Import the visualization class
from gui.integrated_recording_interface import IntegratedRecordingInterface


def wait_qt(ms=50):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    end = time.time() + (ms / 1000.0)
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


def feed_points(ui, start_t=0.0, total_sec=20.0, step=0.05, base_pitch=60.0):
    """
    Feed synthetic time/pitch frames into the UI's visualizer using the expected add path.
    We simulate stable has_pitch with light jitter.
    """
    t = start_t
    while t <= start_t + total_sec:
        pitch = base_pitch + 2.0 * math.sin(t * 2.0 * math.pi / 3.0)
        pkt = {
            'timestamp': time.time(),
            'global_time': t,
            'frequency': 440.0 * (2 ** ((pitch - 69.0)/12.0)),
            'confidence': 0.95,
            'has_pitch': True,
            'note_info': {'midi': pitch}
        }
        try:
            ui.visualizer.add_pitch_data(pkt)
        except Exception:
            traceback.print_exc()
            raise
        t += step
        if int((t-start_t)/step) % 6 == 0:
            wait_qt(1)


def extract_visible_points(ui):
    vis = ui.visualizer
    pts = []
    # Try sources in order: segment PathCollections, batched points, provisional line
    try:
        if hasattr(vis, '_segment_points') and vis._segment_points:
            for pc in vis._segment_points:
                try:
                    off = pc.get_offsets()
                    if off is not None and len(off) > 0:
                        for x, y in off:
                            pts.append((float(x), float(y)))
                except Exception:
                    pass
        bp = getattr(vis, '_batched_points', None)
        if bp is not None:
            try:
                off = bp.get_offsets()
                if off is not None and len(off) > 0:
                    for x, y in off:
                        pts.append((float(x), float(y)))
            except Exception:
                pass
        pl = getattr(vis, '_provisional_line', None)
        if pl is not None and pl.get_visible():
            xs, ys = pl.get_data()
            if xs is not None and ys is not None:
                pts.extend(list(zip([float(x) for x in xs], [float(y) for y in ys])))
    except Exception:
        traceback.print_exc()
    return pts


def assert_true(cond, msg):
    if not cond:
        raise AssertionError(msg)


def main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    ui = IntegratedRecordingInterface()
    ui.show()  # Not actually displayed in Agg
    wait_qt(50)
    # 启用cap诊断日志
    try:
        ui.visualizer.debug_flags['cap_diag'] = True
    except Exception:
        pass

    # Configure analyzing/accompaniment-like state
    ui.visualizer.time_offset = 0.0
    ui.visualizer.time_window = 20.0
    ui.visualizer.is_analyzing = True
    ui.visualizer.backing_mode = 'accompaniment'  # emulate accompaniment path

    # 1) Feed 20s of data, check we have points and line
    feed_points(ui, 0.0, 20.0)
    ui.visualizer.update_display()
    wait_qt(50)
    pts_pre = extract_visible_points(ui)
    assert_true(len(pts_pre) > 50, 'Precondition: not enough visible points after feed (analyzing)')

    # 2) Seek back to 10s (cap at 10s); ensure older <=10s should remain visible
    ui.visualizer.notify_seek(10.0)
    ui.visualizer.update_display()
    wait_qt(200)

    pts_after_seek = extract_visible_points(ui)
    assert_true(any(x <= 10.0 + 1e-3 for x, _ in pts_after_seek), 'Seek: <=10s points should remain visible (analyzing)')
    assert_true(len(pts_after_seek) > 0, 'Seek: should render immediately, not empty (analyzing)')

    # 3) Continue feeding from 10s onward for 3s; we should see new points >10s quickly
    feed_points(ui, 10.0, total_sec=3.0)
    ui.visualizer.update_display()
    wait_qt(200)
    pts_after_more = extract_visible_points(ui)
    assert_true(any(x > 10.3 for x, _ in pts_after_more), 'Post-seek: new segments/points should appear quickly (analyzing)')

    # 4) Ensure no rollback reappearance beyond cap: seek back again to 8s and verify all points have x <= 8.x
    ui.visualizer.notify_seek(8.0)
    ui.visualizer.update_display()
    wait_qt(200)
    pts_cap = extract_visible_points(ui)
    assert_true(all(x <= 8.0001 for x, _ in pts_cap), 'Cap: points beyond cap should not reappear (analyzing)')

    print('OK: validate_seek_cap_analyzing passed')


if __name__ == '__main__':
    main()
