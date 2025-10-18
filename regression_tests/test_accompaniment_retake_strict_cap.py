import os, sys, time, math, traceback

# Non-interactive backend
try:
    import matplotlib
    matplotlib.use('Agg')
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)

# Qt
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
        time.sleep(0.004)


def feed_points(vis, start_t, end_t, step=0.05, base_pitch=60.0):
    t = float(start_t)
    while t <= end_t + 1e-9:
        pitch = base_pitch + 2.0 * math.sin(t * 2.0 * math.pi / 3.0)
        pkt = {
            'timestamp': time.time(),
            'global_time': t,
            'frequency': 440.0 * (2 ** ((pitch - 69.0)/12.0)),
            'confidence': 0.95,
            'has_pitch': True,
            'note_info': {'midi': pitch}
        }
        vis.add_pitch_data(pkt)
        t += step
        if int((t-start_t)/step) % 6 == 0:
            wait_qt(2)


def get_all_offsets(vis):
    pts = []
    # Segment points
    try:
        sps = getattr(vis, '_segment_points', None)
        if sps:
            for pc in sps:
                try:
                    off = pc.get_offsets()
                    if off is not None:
                        for x, y in off:
                            pts.append((float(x), float(y)))
                except Exception:
                    pass
    except Exception:
        pass
    # Batched points
    try:
        bp = getattr(vis, '_batched_points', None)
        if bp is not None:
            off = bp.get_offsets()
            if off is not None:
                for x, y in off:
                    pts.append((float(x), float(y)))
    except Exception:
        pass
    # Main line
    try:
        pl = getattr(vis, 'pitch_line', None)
        if pl is not None:
            xs, ys = pl.get_data()
            if xs is not None and ys is not None:
                for x, y in zip(xs, ys):
                    pts.append((float(x), float(y)))
    except Exception:
        pass
    return pts


def assert_true(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_flow():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    ui = IntegratedRecordingInterface()
    vis = ui.visualizer
    ui.show()
    wait_qt(60)

    # 启用伴奏模式模拟（锁定轴），设置录音/分析上下文
    vis._backing_axis_locked = True
    vis._backing_axis_length = 30.0
    vis.backing_mode = 'accompaniment'
    vis.is_analyzing = True
    vis.is_recording_active = True

    vis.time_window = 16.0
    vis.time_offset = 0.0

    # 1) 先喂 0-30s 数据
    feed_points(vis, 0.0, 30.0)
    vis.update_display(); wait_qt(120)
    # 先在起始窗口检查可见点，然后滚动到末端再检查 >28s
    ui.visualizer.on_horizontal_scroll(0)
    wait_qt(60)
    pre_pts_start = get_all_offsets(vis)
    assert_true(len(pre_pts_start) > 0, 'pre-feed: should render some points at start window')
    ui.visualizer.on_horizontal_scroll(100)
    wait_qt(80)
    pre_pts_end = get_all_offsets(vis)
    assert_true(any(x > 28.0 for x,_ in pre_pts_end), 'pre-feed: after scrolling to end, should see >28s points')

    # 2) 暂停+回退到10s
    vis.is_recording_paused = True
    vis.notify_seek(10.0)
    vis.update_display(); wait_qt(200)

    # 断言：<=10s 历史必须仍可见；>10s 旧点不应可见
    pts_after_seek = get_all_offsets(vis)
    assert_true(any(x <= 10.0001 for x,_ in pts_after_seek), 'rollback: <=10s history must be visible')
    assert_true(all(x <= 10.0001 for x,_ in pts_after_seek), 'rollback: >10s old points must NOT be visible')

    # 3) 暂停状态下左右滚动浏览（应仍不出现>10s旧点）
    for v in [0, 20, 40, 60, 80, 100, 0, 50]:
        try:
            ui.visualizer.on_horizontal_scroll(v)
        except Exception:
            pass
        wait_qt(50)
        pts_scroll = get_all_offsets(vis)
        assert_true(all(x <= 10.0001 for x,_ in pts_scroll), f'scroll@{v}: should not show >10s old points')

    # 4) 模拟倒计时 3s（这里直接设置标志以覆盖真实计时器）
    vis._enable_retake_countdown = True
    vis._force_retake_countdown_once = True
    vis.is_recording = True
    vis.is_recording_active = True
    vis.is_recording_paused = False
    vis.notify_seek(10.0)
    vis.update_display(); wait_qt(80)
    # 倒计时期间：不应出现>10s 旧点
    pts_during_cd = get_all_offsets(vis)
    assert_true(all(x <= 10.0001 for x,_ in pts_during_cd), 'countdown: must not show >10s old points')

    # 5) 倒计时结束后从10s继续喂新数据（10.0~13.0），应立刻出现 >10s 的新点，但旧点不能回潮
    feed_points(vis, 10.0, 13.0)
    vis.update_display(); wait_qt(200)
    pts_after_new = get_all_offsets(vis)
    assert_true(any(x > 10.30 for x,_ in pts_after_new), 'post-countdown: new points >10.3s should be visible quickly')
    assert_true(all(x <= 13.0001 for x,_ in pts_after_new), 'post-countdown: no ghost beyond new data upper bound (sanity)')

    # 严格：确认所有可见点中“>10s”的都是新喂的范围（<=13s），不包含 10-30s 旧回退区
    assert_true(all((x <= 10.0001) or (10.0 - 1e-4 <= x <= 13.0001) for x,_ in pts_after_new), 'post-countdown: must not include old rollback-area >13s')

    print('OK: test_accompaniment_retake_strict_cap passed')


if __name__ == '__main__':
    test_flow()
