"""
统一的音高检测服务（Phase 1）
- 提供一个稳定、轻量的 YIN 基线检测作为主路径
- 与性能模式联动，做轻微阈值自适应
- 暴露 detect(frame) -> (f0_raw, confidence) 简单接口

注意：本服务只做原始 f0 提取与简单置信度估计；
      平滑/可视化/进一步谐波上修仍在调用方完成（逐步迁移）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple
import numpy as np


@dataclass
class PitchServiceConfig:
    sample_rate: float = 48000.0
    min_frequency: float = 80.0
    max_frequency: float = 1047.0
    yin_threshold: float = 0.12
    mode_name: str = "BALANCED"  # QUIET | BALANCED | HIGH_PERFORMANCE


class PitchDetectionService:
    def __init__(self,
                 sample_rate: float = 48000.0,
                 min_frequency: float = 80.0,
                 max_frequency: float = 1047.0,
                 yin_threshold: float = 0.12,
                 mode_name: str = "BALANCED"):
        self.cfg = PitchServiceConfig(
            sample_rate=float(sample_rate),
            min_frequency=float(min_frequency),
            max_frequency=float(max_frequency),
            yin_threshold=float(yin_threshold),
            mode_name=str(mode_name)
        )
        # 缓存汉宁窗，避免重复分配
        self._hann_len = 0
        self._hann = None
        self._cmndf_idx_len = 0
        self._cmndf_idx = None

    # -------- 配置 API --------
    def set_frequency_range(self, min_f: float, max_f: float):
        self.cfg.min_frequency = float(min_f)
        self.cfg.max_frequency = float(max_f)

    def set_sample_rate(self, sr: float):
        """更新内部采样率配置，并重置与采样率相关的内部缓存。"""
        try:
            sr_f = float(sr)
        except Exception:
            return
        if sr_f <= 0:
            return
        if getattr(self.cfg, 'sample_rate', None) != sr_f:
            self.cfg.sample_rate = sr_f
            # 采样率变化时，重置窗口缓存，避免长度不匹配
            self._hann_len = 0
            self._hann = None

    def apply_config(self, pm_config) -> None:
        """从性能管理器配置同步必要参数（轻量）。"""
        try:
            if hasattr(pm_config, 'yin_threshold'):
                self.cfg.yin_threshold = float(pm_config.yin_threshold)
        except Exception:
            pass
        try:
            # 仅记录模式名用于轻微阈值自适应
            mode_name = getattr(pm_config, 'mode_name', None)
            if isinstance(mode_name, str):
                self.cfg.mode_name = mode_name
        except Exception:
            pass

    # -------- 检测入口 --------
    def detect(self, frame: np.ndarray) -> Tuple[float, float]:
        """返回 (f0_raw, confidence)，失败返回 (0.0, 0.0)。

        confidence 基于 YIN CMNDF 谷深：深谷→高置信度(≈1.0)，浅谷→低置信度(≈0.0)。
        该值用于 VAD/噪声门控的静音判别，拒绝噪声环境下的伪周期检测。
        """
        try:
            f0, conf = self._yin_detect(frame)
            if f0 <= 0:
                return 0.0, 0.0
            return float(f0), float(conf)
        except Exception:
            return 0.0, 0.0

    # -------- 内部：YIN（FFT-CMNDF） --------
    def _yin_detect(self, audio_data: np.ndarray):
        """返回 (f0, confidence)。f0<=0 表示检测失败。"""
        try:
            x_in = np.asarray(audio_data, dtype=np.float64)
            if x_in.ndim > 1:
                x_in = x_in.reshape(-1)
            if x_in.size < 64:
                return 0.0, 0.0
            sr = float(self.cfg.sample_rate)
            # 使用全长作为分析窗口（调用方负责确保帧窗足够）
            x = x_in
            # 高采样率下的x2降采样（>=88.2k）
            if sr >= 88000.0 and x.size >= 1024:
                x = x[::2]
                sr = sr / 2.0

            # 去均值 + 汉宁窗缓存
            if self._hann_len != x.size:
                self._hann = np.hanning(x.size)
                self._hann_len = x.size
            x = (x - float(np.mean(x))) * self._hann

            N = x.size
            ui_min_f = float(self.cfg.min_frequency)
            ui_max_f = float(self.cfg.max_frequency)
            tau_min = int(max(2, np.floor(sr / max(ui_max_f, 1.0))))
            tau_max = int(min(N - 3, np.ceil(sr / max(ui_min_f, 50.0))))
            if tau_max <= tau_min + 2:
                return 0.0, 0.0

            # FFT自相关 -> 差分近似 d(tau) = 2*(r(0)-r(tau))
            nfft = 1 << (2 * N - 1).bit_length()
            spec = np.fft.rfft(x, n=nfft)
            ac = np.fft.irfft(spec * np.conj(spec), n=nfft)[:N]
            ac0 = float(ac[0])
            d = 2.0 * (ac0 - ac[:tau_max + 1])

            # CMNDF
            d1 = d[1:tau_max + 1]
            if np.any(d1 < 0):
                d1 = np.maximum(d1, 0.0)
            cumsum = np.cumsum(d1)
            if self._cmndf_idx_len != d1.size:
                self._cmndf_idx = np.arange(1, d1.size + 1, dtype=np.float64)
                self._cmndf_idx_len = d1.size
            idx = self._cmndf_idx
            cmndf = np.ones_like(d)
            denom = cumsum / idx
            denom = np.where(denom <= 1e-12, 1e-12, denom)
            cmndf[1:tau_max + 1] = d1 / denom

            # 阈值（按模式轻微自适应）
            yin_thr = float(self.cfg.yin_threshold)
            mode = (self.cfg.mode_name or "BALANCED").upper()
            if mode.endswith("HIGH_PERFORMANCE"):
                yin_thr = max(0.08, yin_thr - 0.02)
            elif mode.endswith("BALANCED"):
                yin_thr = max(0.10, yin_thr - 0.01)

            search = cmndf[tau_min:tau_max + 1]
            below = np.where(search < yin_thr)[0]
            if below.size > 0:
                start = int(below[0])
                s0 = tau_min + start
                s1 = min(tau_max, s0 + 8)
                loc = int(np.argmin(cmndf[s0:s1 + 1]))
                cand_tau = s0 + loc
            else:
                cand_tau = int(np.argmin(cmndf[tau_min:tau_max + 1]) + tau_min)

            if not (tau_min <= cand_tau <= tau_max):
                return 0.0, 0.0

            # 抛物线插值（在CMNDF曲线）
            if 1 < cand_tau < cmndf.size - 1:
                y1, y2, y3 = cmndf[cand_tau - 1], cmndf[cand_tau], cmndf[cand_tau + 1]
                denom_q = (y1 - 2 * y2 + y3)
                off = 0.0 if abs(denom_q) < 1e-12 else 0.5 * (y1 - y3) / denom_q
            else:
                off = 0.0
            tau_hat = float(cand_tau) + float(np.clip(off, -1.0, 1.0))
            if tau_hat <= 1e-6:
                return 0.0, 0.0
            f0 = float(sr / tau_hat)
            if not (ui_min_f <= f0 <= ui_max_f * 1.02):
                return 0.0, 0.0
            # 置信度：来自 CMNDF 谷深
            # cmndf 值近 0 → 强周期性 → 高置信；近 1 → 弱/无周期 → 低置信
            cmndf_val = float(cmndf[cand_tau])
            conf = float(np.clip(1.0 - cmndf_val, 0.0, 1.0))
            return f0, conf
        except Exception:
            return 0.0, 0.0
