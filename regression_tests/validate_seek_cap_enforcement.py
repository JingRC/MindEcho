import os, sys, time, math
import traceback

try:
    import matplotlib
    matplotlib.use('Agg')
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)

try:
    from qtpy import QtWidgets
except Exception:
    try:
        from PyQt5 import QtWidgets  # type: ignore
    except Exception:
        from PyQt6 import QtWidgets  # type: ignore

from gui.integrated_recording_interface import IntegratedRecordingInterface


def wait_qt(ms=40):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    end = time.time() + ms/1000.0
    while time.time() < end:
        app.processEvents()
        time.sleep(0.004)


def feed(ui, start, dur, step=0.05, base_pitch=60.0):
    t = start
    while t <= start + dur + 1e-9:
        pitch = base_pitch + 1.5*math.sin(t*2.0*math.pi/4.0)
        pkt = {
            'timestamp': time.time(),
            'global_time': t,
            'frequency': 440.0 * (2 ** ((pitch - 69.0)/12.0)),
            'confidence': 0.9,
            'has_pitch': True,
            'note_info': {'midi': pitch}
        }
        ui.visualizer.add_pitch_data(pkt)
        t += step
        if int((t-start)/step) % 10 == 0:
            wait_qt(1)


def collect_all_offsets(viz):
    pts = []
    import numpy as np
    # segment points
    if hasattr(viz, '_segment_points') and viz._segment_points:
        for coll in viz._segment_points:
            try:
                off = coll.get_offsets()
                if off is not None and len(off) > 0:
                    arr = np.asarray(off)
                    for x, y in arr:
                        pts.append((float(x), float(y)))
            except Exception:
                pass
    # batched
    bp = getattr(viz, '_batched_points', None)
    if bp is not None:
        try:
            off = bp.get_offsets()
            if off is not None and len(off) > 0:
                for x, y in off:
                    pts.append((float(x), float(y)))
        except Exception:
            pass
    # fallback
    fb = getattr(viz, '_browse_points_fallback', None)
    if fb is not None:
        try:
            off = fb.get_offsets()
            if off is not None and len(off) > 0:
                for x, y in off:
                    pts.append((float(x), float(y)))
        except Exception:
            pass
    # head
    hp = getattr(viz, '_head_points_scatter', None)
    if hp is not None:
        try:
            off = hp.get_offsets()
            if off is not None and len(off) > 0:
                for x, y in off:
                    pts.append((float(x), float(y)))
        except Exception:
            pass
    # main line
    ml = getattr(viz, 'pitch_line', None)
    if ml is not None:
        try:
            xs, ys = ml.get_data()
            if xs is not None and ys is not None:
                for x, y in zip(xs, ys):
                    pts.append((float(x), float(y)))
        except Exception:
            pass
    return pts


def assert_true(c, msg):
    if not c:
        raise AssertionError(msg)


def main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    ui = IntegratedRecordingInterface()
    ui.show(); wait_qt(50)
    ui.is_recording = True; ui.is_analyzing = True
    feed(ui, 0.0, 25.0)
    ui.visualizer.update_display(); wait_qt(120)

    # Seek back to 12s
    ui._apply_backing_seek(12.0)
    ui.visualizer.update_display(); wait_qt(200)
    cap = float(getattr(ui.visualizer, '_max_visible_time', 0.0))
    assert_true(abs(cap - 12.0) < 0.01, 'cap should equal seek target')
    pts = collect_all_offsets(ui.visualizer)
    assert_true(len(pts) > 50, 'expect many points left of cap after seek')
    assert_true(all(x <= cap + 1e-6 for x,_ in pts), 'no point should exceed cap immediately after seek')

    # Inject an artificial future point >cap to simulate late arrival / race
    rogue_pkt = {
        'timestamp': time.time(),
        'global_time': cap + 5.0,
        'frequency': 440.0,
        'confidence': 0.95,
        'has_pitch': True,
        'note_info': {'midi': 69}
    }
    ui.visualizer.add_pitch_data(rogue_pkt)
    # Force several display cycles during enforcement window
    for _ in range(5):
        ui.visualizer.update_display(); wait_qt(60)
    pts2 = collect_all_offsets(ui.visualizer)
    assert_true(all(x <= cap + 1e-6 for x,_ in pts2), 'enforcement should purge rogue >cap point')
    print('OK: validate_seek_cap_enforcement passed')


if __name__ == '__main__':
    main()
