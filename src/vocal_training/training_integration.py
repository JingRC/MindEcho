"""练声模式集成层 — 轻量桥接主窗口与练声模块

在主窗口的音频处理管线中插入练声模式的轻量路径：
  - 跳过 VAD / 假声分类 / 换气检测 / 声部分离
  - 保留 YIN 音高检测
  - 结果直送 TrainingEngine → TrainingVisualizer

用法 (在主窗口 __init__ 或 setup 中):
    from src.vocal_training.training_integration import TrainingIntegration
    self._training = TrainingIntegration(self)
    self._training.attach()
"""

from __future__ import annotations

import time
from typing import Optional

import numpy as np

from src.vocal_training.training_panel import TrainingPanel


class TrainingIntegration:
    """练声模式与主窗口的桥接层。

    职责:
      - 管理 TrainingPanel 的显示/隐藏
      - 在音频处理管线中提供轻量音高通道
      - 管理伴奏输出流和音频混音
    """

    def __init__(self, main_window: "IntegratedRecordingInterface"):
        self._main = main_window
        self._panel: Optional[TrainingPanel] = None
        self._active = False

        # 轻量管线标志
        self._use_lightweight_pipeline = False

        # 统计
        self._pitch_feed_count = 0
        self._last_feed_time = 0.0

    # ── 公开属性 ─────────────────────────────────────

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def panel(self) -> Optional[TrainingPanel]:
        return self._panel

    @property
    def training_duration(self) -> float:
        """当前练声时长（含会话累计 + 当前练习已用）。"""
        if self._panel is None:
            return 0.0
        return (getattr(self._panel, '_session_duration', 0.0)
                + getattr(self._panel, '_current_exercise_duration', 0.0))

    # ── 生命周期 ─────────────────────────────────────

    def attach(self) -> None:
        """将练声面板挂载到主窗口。"""
        if self._panel is None:
            self._panel = TrainingPanel(self._main)
            self._panel.panel_closed.connect(self.deactivate)
            # 设置音频输入提供者回调 — 点击"开始练声"时延迟启动/停止录音
            self._panel._audio_input_provider = self.ensure_audio_input
            self._panel._audio_input_stopper = self.stop_audio_input
            # 确保面板初始隐藏，避免未加入布局时在 (0,0) 处渲染文字
            self._panel.hide()

    def activate(self) -> None:
        """激活练声模式（轻量管线 + 标记激活）。"""
        if self._panel is None:
            self.attach()
        self._active = True
        self._use_lightweight_pipeline = True
        # 🎯 强制完整音高状态机处理：训练模式需要谐波纠错，不受 display_mode 影响
        try:
            ap = getattr(self._main, 'audio_processor', None)
            if ap is not None:
                ap._force_full_display_processing = True
        except Exception:
            pass
        # 不重置音高分析状态 — 保留普通模式的状态历史，
        # 让 _compute_normal_mode_display_frequency 的谐波纠错和尖峰过滤
        # 有连续的上下文参考，避免训练模式前几帧识别错误。
        # 同步 Profile 训练等级到面板（无存档时默认入门）
        try:
            stats = self.get_profile_training_stats()
            lvl = stats.get("level", "beginner") if stats else "beginner"
            self._panel.set_auto_level(lvl)
        except Exception:
            self._panel.set_auto_level("beginner")

    def deactivate(self) -> None:
        """停用练声模式，恢复普通管线。"""
        self._active = False
        self._use_lightweight_pipeline = False
        # 恢复 display_mode 对音高状态机的控制
        try:
            ap = getattr(self._main, 'audio_processor', None)
            if ap is not None:
                ap._force_full_display_processing = False
        except Exception:
            pass

        # 停止由练声模式启动的录音（不影响用户手动启动的录音）
        if getattr(self, '_training_owns_recording', False):
            try:
                ap = getattr(self._main, 'audio_processor', None)
                if ap is not None:
                    ap.stop_recording()
                self._main.is_recording = False
                self._main.is_analyzing = False
                print("[TrainingIntegration] 已停止练声录音")
            except Exception as _e:
                print(f"[TrainingIntegration] 停止录音失败: {_e}")
            self._training_owns_recording = False

    def toggle(self) -> bool:
        """切换练声模式开/关。返回新状态。"""
        if self._active:
            self.deactivate()
        else:
            self.activate()
        return self._active

    def stop_audio_input(self) -> None:
        """停止由练声模式启动的录音（练习结束时调用）。"""
        if not getattr(self, '_training_owns_recording', False):
            return
        try:
            ap = getattr(self._main, 'audio_processor', None)
            if ap is not None:
                ap.stop_recording()
            self._main.is_recording = False
            self._main.is_analyzing = False
            self._training_owns_recording = False
            print("[TrainingIntegration] 已停止练声录音")
        except Exception as _e:
            print(f"[TrainingIntegration] 停止录音失败: {_e}")

    def ensure_audio_input(self) -> bool:
        """确保音频输入流和处理线程在运行。

        由 TrainingPanel._start_exercise() 调用，启动麦克风采集。
        使用录音路径（不保存文件）——与唱歌模式相同的设备选择和音高管道。

        Returns:
            True if audio input is running (or was already running).
        """
        if not self._active or self._panel is None:
            return False

        ap = getattr(self._main, 'audio_processor', None)
        if ap is None:
            print("[TrainingIntegration] 无法获取 audio_processor")
            return False

        ap_active = getattr(ap, 'is_global_monitoring_active', False)
        ap_recording = getattr(ap, 'is_recording', False)
        ap_processing = getattr(ap, 'is_audio_processing', False)
        main_is_recording = getattr(self._main, 'is_recording', False)

        # 任一标志表明音频管道已在运行 → 不重复启动
        if ap_active or ap_recording or main_is_recording:
            # 已在运行，只需确保标志位正确
            try:
                ap.is_monitoring_only = False
                ap.enable_pitch_visualization = True
            except Exception:
                pass
            if not ap_processing:
                ap.start_audio_processing_thread()
            print("[TrainingIntegration] 音频已运行，跳过启动")
            return True

        print("[TrainingIntegration] 启动音频输入（录音路径，不保存文件）...")
        try:
            # 🎯 训练模式：保留音高分析状态机历史，避免前几帧识别错误
            # _reset_pitch_analysis_state() 在 start_recording() 中会清空状态，
            # 通过此标志告诉 start_recording 跳过状态重置。
            try:
                ap._preserve_pitch_state = True
            except Exception:
                pass
            ok = ap.start_recording(filename=None, should_save=False)
            try:
                ap._preserve_pitch_state = False
            except Exception:
                pass
            if ok:
                self._training_owns_recording = True
                print("[TrainingIntegration] 音频输入已启动")
                return True
        except Exception as _e:
            print(f"[TrainingIntegration] 录音路径失败: {_e}")

        # 回退：monitoring 路径
        try:
            try:
                ap._preserve_pitch_state = True
            except Exception:
                pass
            ap.start_monitoring()
            try:
                ap._preserve_pitch_state = False
            except Exception:
                pass
            ap.is_monitoring_only = False
            ap.enable_pitch_visualization = True
            print("[TrainingIntegration] 已通过监听路径启动")
            return True
        except Exception as _e:
            print(f"[TrainingIntegration] 监听路径也失败: {_e}")

        return False

    def feed_pitch(self, freq_hz: float, confidence: float = 0.9, rms: float = 0.0) -> None:
        """向练声面板喂入实时音高数据。

        由主窗口音频处理循环直接调用，跳过所有重 DSP。
        始终喂入可视化器让用户看到音高线与目标音符的关系；
        评分在面板内部根据 _is_running 自行决定是否处理。
        """
        if not self._active or self._panel is None:
            return
        try:
            self._panel.feed_pitch(freq_hz, confidence, rms)
            self._pitch_feed_count += 1
            self._last_feed_time = time.time()

            # 定期日志
            if self._pitch_feed_count % 60 == 1:
                print(f"[Integration] feed_pitch #{self._pitch_feed_count} | "
                      f"freq={freq_hz:.1f}Hz conf={confidence:.2f} rms={rms:.3f} active={self._active}")
        except Exception:
            pass

    def save_training_result(self, score: "ExerciseScore") -> None:
        """将练声结果存入当前活跃存档。

        由主窗口在 exercise_completed 信号中调用。
        """
        try:
            profile_mgr = getattr(self._main, '_profile_manager', None)
            active_id = ""
            if profile_mgr is not None:
                active = profile_mgr.get_active_profile()
                if active is not None:
                    active_id = active.id

            if profile_mgr is None:
                return

            from src.profiles.profile_model import TrainingRecord
            # 获取本次练习用时
            exercise_dur = getattr(self._panel, '_current_exercise_duration', 0.0)
            record = TrainingRecord(
                exercise_id=score.exercise_id,
                exercise_name=score.exercise_id,  # 可从练习库补全名称
                total_score=score.total_score,
                level=score.overall_level.name,
                pitch_accuracy=score.pitch_accuracy,
                stability=score.stability,
                timing=score.timing,
                hold=score.hold,
                perfect_count=score.perfect_count,
                great_count=score.great_count,
                good_count=score.good_count,
                ok_count=score.ok_count,
                miss_count=score.miss_count,
                max_streak=score.max_streak,
                tolerance_level=getattr(self._panel, '_auto_level', 'intermediate'),
                duration_seconds=round(exercise_dur, 1),
                avg_frame_hit_rate=round(score.avg_frame_hit_rate, 3),
                avg_transition_time=round(score.avg_transition_time, 3),
                date=time.strftime("%Y-%m-%dT%H:%M:%S"),
            )
            # 补全练习名称
            try:
                from src.vocal_training.exercise_library import get_exercise
                ex = get_exercise(score.exercise_id)
                if ex:
                    record.exercise_name = ex.name
            except Exception:
                pass

            profile_mgr.add_training_record(active_id, record)
        except Exception:
            pass

    def get_profile_training_stats(self) -> Optional[dict]:
        """获取当前活跃存档的训练统计（供 UI 显示）。"""
        try:
            profile_mgr = getattr(self._main, '_profile_manager', None)
            if profile_mgr is None:
                return None
            active = profile_mgr.get_active_profile()
            if active is None:
                return None
            ts = active.training_stats
            return {
                "level": ts.level,
                "level_progress": ts.level_progress,
                "total_sessions": ts.total_sessions,
                "average_score": ts.average_score,
                "best_score": ts.best_score,
                "best_exercise": ts.best_exercise,
                "recent_count": len(ts.recent_records),
            }
        except Exception:
            return None

    def set_sample_rate(self, sr: int) -> None:
        """通知练声面板采样率变化。"""
        if self._panel:
            try:
                self._panel.set_sample_rate(sr)
            except Exception:
                pass

    def get_mixed_audio(self, n_samples: int) -> Optional[np.ndarray]:
        """获取伴奏混音块（用于叠加到回听/监听音频流）。

        返回值: float32 shape=(n,1) 伴奏单声道，或 None（无伴奏）
        """
        if not self._active or self._panel is None:
            return None
        try:
            accomp = self._panel._accompaniment
            if accomp and accomp.is_playing:
                chunk = accomp.get_audio_chunk(n_samples)
                # 混合为单声道
                return (chunk[:, 0] + chunk[:, 1]).reshape(-1, 1).astype(np.float32) * 0.5
        except Exception:
            pass
        return None

    # ── 轻量管线参数 ─────────────────────────────────

    def configure_lightweight_params(self) -> dict:
        """返回轻量管线的推荐参数，供主窗口的音频处理循环使用。

        Returns:
            dict with keys: skip_vad, skip_falsetto, skip_breath,
                           skip_lfm, fast_pitch_path
        """
        return {
            "skip_vad": True,
            "skip_falsetto_classification": True,
            "skip_breath_detection": True,
            "skip_lfm_selection": True,
            "skip_noise_reduction": False,  # 保留轻量降噪
            "pitch_confidence_threshold": 0.35,  # 降低门限 (练声用)
        }
