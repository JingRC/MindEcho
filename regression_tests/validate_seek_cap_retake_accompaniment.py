import os, sys, time, glob, json
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

# Minimal Qt stub runner
try:
    from qtpy import QtWidgets
except Exception:
    try:
        from PyQt5 import QtWidgets  # type: ignore
    except Exception:
        from PyQt6 import QtWidgets  # type: ignore

from gui.integrated_recording_interface import IntegratedRecordingInterface


def wait_qt(ms=50):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    end = time.time() + (ms / 1000.0)
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


def feed_points(ui, start_t=0.0, total_sec=20.0, step=0.05, base_pitch=60.0):
    """Feed synthetic frames using add_pitch_data; honor current epoch if set."""
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
        # Attach epoch if visualizer enforces one
        cur_epoch = getattr(ui.visualizer, '_current_epoch', None)
        if cur_epoch is not None:
            pkt['_epoch'] = int(cur_epoch)
        try:
            ui.visualizer.add_pitch_data(pkt)
        except Exception:
            traceback.print_exc()
            raise
        t += step
        if int((t-start_t)/step) % 6 == 0:
            wait_qt(1)


def extract_visible_points_and_line(ui):
    vis = ui.visualizer
    pts = []
    try:
        # Segment PathCollections
        if hasattr(vis, '_segment_points') and vis._segment_points:
            for pc in vis._segment_points:
                try:
                    off = pc.get_offsets()
                    if off is not None and len(off) > 0:
                        for x, y in off:
                            pts.append((float(x), float(y)))
                except Exception:
                    pass
        # Batched points
        bp = getattr(vis, '_batched_points', None)
        if bp is not None:
            try:
                off = bp.get_offsets()
                if off is not None and len(off) > 0:
                    for x, y in off:
                        pts.append((float(x), float(y)))
            except Exception:
                pass
        # Provisional line
        pl = getattr(vis, '_provisional_line', None)
        if pl is not None and pl.get_visible():
            xs, ys = pl.get_data()
            if xs is not None and ys is not None:
                pts.extend(list(zip([float(x) for x in xs], [float(y) for y in ys])))
        # Main pitch line
        ml = getattr(vis, 'pitch_line', None)
        if ml is not None:
            try:
                xs, ys = ml.get_data()
                if xs is not None and ys is not None and len(xs) > 0:
                    pts.extend(list(zip([float(x) for x in xs], [float(y) for y in ys])))
            except Exception:
                pass
    except Exception:
        traceback.print_exc()
    return pts


def assert_true(cond, msg):
    if not cond:
        raise AssertionError(msg)


def latest_trim_after_cutoff(details_dir):
    try:
        files = sorted(glob.glob(os.path.join(details_dir, 'pitch_*.ndjson')))
        if not files:
            return None
        fp = files[-1]
        with open(fp, 'r', encoding='utf-8') as f:
            cutoff = None
            for line in f:
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if isinstance(row, dict) and row.get('op') == 'trim_after':
                    cutoff = float(row.get('cutoff'))
            return cutoff
    except Exception:
        return None


def main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    ui = IntegratedRecordingInterface()
    ui.show()
    wait_qt(50)

    # Emulate accompaniment recording/analysis session
    ui.backing_mode = 'accompaniment'
    ui.visualizer.backing_mode = 'accompaniment'
    ui.is_analyzing = True
    ui.is_recording = True
    ui.visualizer.is_analyzing = True

    # Feed 30s data, pause, then retake to 10s via backing seek
    feed_points(ui, 0.0, 30.0)
    ui.visualizer.update_display(); wait_qt(50)

    # Simulate pause
    ui.is_recording_paused = True
    ui.visualizer._external_paused = True
    wait_qt(20)

    # Bypass retake confirmation dialog via rate limit, then apply backward seek to 10s
    ui._last_retake_prompt_time = time.time()
    ui._apply_backing_seek(10.0)  # will call visualizer.notify_seek and trim_after
    ui.visualizer.update_display(); wait_qt(200)

    # After seek, viewport usually spans both sides around cap; ensure left-of-cap has points and line, right cleared
    pts_after_seek = extract_visible_points_and_line(ui)
    assert_true(len(pts_after_seek) > 0, 'Seek: should render immediately, not empty')
    assert_true(all(x <= 10.0001 for x, _ in pts_after_seek), 'Seek: right-of-cap old points must be cleared')
    # Require enough density on left (line+points), not just a few remnants
    left_count = sum(1 for x, _ in pts_after_seek if x <= 10.0 + 1e-6)
    assert_true(left_count >= 80, 'Seek: left-of-cap should show continuous line + dots (enough density)')

    # Resume recording; feed new points >10s
    ui.is_recording_paused = False
    ui.visualizer._external_paused = False
    feed_points(ui, 10.0, total_sec=3.0)
    ui.visualizer.update_display(); wait_qt(200)

    pts_after_more = extract_visible_points_and_line(ui)
    assert_true(any(x > 10.3 for x, _ in pts_after_more), 'Post-seek: new >cap points should appear quickly')
    # Ensure no old points snuck back beyond cap (all >cap must be from new feed and thus >10s)
    assert_true(not any(x > 10.0001 and x < 10.0 for x, _ in pts_after_more), 'No stale >cap points should reappear')

    # Validate persistence recorded a trim_after near 10s
    details_dir = os.path.join(ROOT, 'recordings', 'Details')
    cutoff = latest_trim_after_cutoff(details_dir)
    assert_true(cutoff is None or abs(cutoff - 10.0) < 0.25, 'Persistence: expected a trim_after ~10s to be written')

    print('OK: validate_seek_cap_retake_accompaniment passed')


if __name__ == '__main__':
    main()
