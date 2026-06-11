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

            # ── 预加重滤波（方案B）──
            # y[n] = x[n] - α·x[n-1], α=0.95 (语音标准范围 0.95-0.97)
            # 作用：补偿声门源 −6dB/oct 滚降，使频谱更平坦。
            # 平坦频谱 → 各频率对自相关贡献更均匀 → CMNDF 谷更尖锐。
            # 对假声/气声：减弱低频呼吸噪声对自相关的污染，保留谐波结构。
            # α=0.95 (非 0.97)：假声谐波已极强，较低 α 避免过度提升
            # 谐波 → 减少 T/2、T/3 等短 τ 伪周期对 CMNDF 的贡献。
            # 注意：此滤波器在加窗后应用，窗边缘衰减避免了滤波器瞬态。
            _preemphasis_alpha = 0.95
            x[1:] = x[1:] - _preemphasis_alpha * x[:-1]
            x[0] *= (1.0 - _preemphasis_alpha)  # 首个样本平滑衰减

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

            # ── 多候选搜集：低于阈值区段 + 最佳超阈值局部谷点 ──
            # 假声/头声时基频很弱，真基频周期 τ=T 的 CMNDF 可能永不跌破
            # 阈值，导致 τ=T 不在候选池中。把超阈值但形态良好的局部谷点
            # 也纳入候选，再靠自相关 + 谐波乘积谱（HPS）综合评分甄别。
            candidates = []  # [(tau, cmndf_val), ...]
            seen_tau: set = set()

            # 阶段 A：低于阈值区段（同前）
            search = cmndf[tau_min:tau_max + 1]
            below = np.where(search < yin_thr)[0]
            if below.size > 0:
                region_start = int(below[0])
                for i in range(1, len(below)):
                    if below[i] > below[i-1] + 6:
                        region_end = int(below[i-1])
                        s0 = tau_min + region_start
                        s1 = min(tau_max, tau_min + region_end + 8)
                        loc = int(np.argmin(cmndf[s0:s1 + 1]))
                        cand = s0 + loc
                        if tau_min <= cand <= tau_max:
                            candidates.append((cand, float(cmndf[cand])))
                            seen_tau.add(cand)
                        region_start = int(below[i])
                region_end = int(below[-1])
                s0 = tau_min + region_start
                s1 = min(tau_max, tau_min + region_end + 8)
                loc = int(np.argmin(cmndf[s0:s1 + 1]))
                cand = s0 + loc
                if tau_min <= cand <= tau_max:
                    candidates.append((cand, float(cmndf[cand])))
                    seen_tau.add(cand)

            # 阶段 B：超阈值局部谷点（补齐假声/头声时缺失的真基频候选）
            # 在 tau_min..tau_max 范围内扫一遍 CMNDF，记录所有局部
            # 最小值点，取 CMNDF 最浅的前 20 个（与已存在的去重）。
            local_minima = []
            prev_val = cmndf[tau_min]
            prev_tau = tau_min
            rising = False
            for tau_i in range(tau_min + 1, tau_max):
                cur = cmndf[tau_i]
                if cur < prev_val:
                    rising = False
                elif cur > prev_val and not rising:
                    # 刚经过一个局部最小值
                    if prev_tau not in seen_tau:
                        local_minima.append((prev_tau, float(prev_val)))
                    rising = True
                prev_val = cur
                prev_tau = tau_i
            # 按 CMNDF 值排序（越低越好），取前 20 个
            local_minima.sort(key=lambda x: x[1])
            for tau_i, cmndf_val_i in local_minima[:20]:
                if tau_min <= tau_i <= tau_max and tau_i not in seen_tau:
                    candidates.append((tau_i, cmndf_val_i))
                    seen_tau.add(tau_i)

            # ── 阶段 C：时序连续邻域先验 ──
            # 假声换音时 τ_prev 单点可能已失效，注入 τ_prev 周围 ±10%
            # 范围内的局部谷点作为候选，确保换音后的真基频也在池中。
            _prev_tau = float(getattr(self, '_yin_prev_tau_hat', 0.0) or 0.0)
            if tau_min <= int(_prev_tau) <= tau_max:
                # 注入 τ_prev 本身
                if int(_prev_tau) not in seen_tau:
                    candidates.append((int(_prev_tau), float(cmndf[int(_prev_tau)])))
                    seen_tau.add(int(_prev_tau))
                # 注入 τ_prev 邻域内的局部谷点（覆盖换音 ±10%）
                _neighbor_lo = max(tau_min, int(_prev_tau * 0.90))
                _neighbor_hi = min(tau_max, int(_prev_tau * 1.10))
                for tau_i, cmndf_val_i in local_minima:
                    if _neighbor_lo <= tau_i <= _neighbor_hi and tau_i not in seen_tau:
                        candidates.append((tau_i, cmndf_val_i))
                        seen_tau.add(tau_i)

            # ── 阶段 D：频谱峰候选（假声高音区关键补充）──
            # G4 及以上假声基频极弱，CMNDF 在真 τ 处可能既不低于阈值、
            # 也不形成局部谷点（仅为上升曲线上的拐点），导致真 τ 永不
            # 进入候选池。但基频在 FFT 量谱中始终存在（虽弱），通过
            # 量谱峰提取可将其作为候选纳入，再靠 HPS 综合评分甄别。
            #
            # v9.3 简化：不设严苛的峰值阈值（原中位数×1.30 对弱基频太严），
            # 改为极宽松阈值（均值×0.35），重点扫描低频区（≤880Hz，基频
            # 不会超过此范围）。取量值前 6 峰 + 最低频峰，确保弱基频不漏。
            # 预计算量谱（后续 HPS 评分也会复用）
            mag_spec = np.abs(spec)
            mean_mag = float(np.mean(mag_spec[1:]))  # 排除DC
            n_bins = len(mag_spec)
            # 只扫描低频区（基频 ≤880Hz，更高频的峰必然是谐波）
            _spec_bin_lo = max(1, int(ui_min_f * float(nfft) / sr))
            _spec_scan_hi = min(n_bins - 1, int(880.0 * float(nfft) / sr))
            _spec_peaks = []  # [(freq_hz, magnitude), ...]
            if _spec_scan_hi > _spec_bin_lo + 3:
                # 极宽松阈值：均值×0.35，假声弱基频也能通过
                _spec_threshold = mean_mag * 0.35
                for _bi in range(_spec_bin_lo + 1, _spec_scan_hi):
                    _mv = mag_spec[_bi]
                    if _mv <= _spec_threshold:
                        continue
                    if _mv > mag_spec[_bi - 1] and _mv > mag_spec[_bi + 1]:
                        _freq_hz = float(_bi) * sr / float(nfft)
                        _spec_peaks.append((_freq_hz, float(_mv)))
                # 按量值降序排列，取前 6 个峰
                _spec_peaks.sort(key=lambda x: x[1], reverse=True)
                _top_peaks = _spec_peaks[:6]
                # 确保最低频峰也被纳入（假声基频量值低但频率最低）
                if _spec_peaks:
                    _lowest_peak = min(_spec_peaks, key=lambda x: x[0])
                    _already_in = any(abs(_pf - _lowest_peak[0]) < 1.0 for _pf, _ in _top_peaks)
                    if not _already_in:
                        _top_peaks.append(_lowest_peak)
                # 将频谱峰转为 τ 候选
                for _pf, _ in _top_peaks:
                    _tau_from_spec = int(sr / _pf)
                    if tau_min <= _tau_from_spec <= tau_max and _tau_from_spec not in seen_tau:
                        candidates.append((_tau_from_spec, float(cmndf[_tau_from_spec])))
                        seen_tau.add(_tau_from_spec)

            # ── 倒谱分析：用于候选验证 ──
            # 倒谱 (cepstrum) = IFFT(log|spectrum|)。对周期性声源极鲁棒：
            # 即使基频在量谱中微弱（假声常见），谐波等间距排列在倒谱中
            # 仍会在真基频周期 τ=T 处形成单峰。CMNDF 在假声高音区常因
            # 基频太弱而偏好谐波候选（τ=3T/4 等），倒谱峰可独立纠正。
            # 计算开销：一次 IFFT + 若干索引查表，可忽略。
            _eps = 1e-10
            _log_spec = np.log(np.maximum(mag_spec, _eps))
            _cepst = np.fft.irfft(_log_spec, n=nfft)
            _cepst_abs = np.abs(_cepst)
            # 在有效 τ 范围内取最大倒谱值用于归一化
            _cepst_roi_end = min(tau_max + 1, len(_cepst_abs))
            _cepst_roi = _cepst_abs[tau_min:_cepst_roi_end]
            _cepst_max = float(np.max(_cepst_roi)) if len(_cepst_roi) > 0 else 1.0

            # ── 谐波一致性验证 + 综合评分 ──
            # mag_spec 已在阶段 D 预计算，此处直接复用。
            if len(candidates) > 1:

                scored = []
                for cand_tau_i, cmndf_val_i in candidates:
                    idx = int(cand_tau_i)
                    # 自相关验证
                    if 0 < idx < len(ac):
                        ac_norm = float(ac[idx]) / max(float(ac[0]), 1e-12)
                    else:
                        ac_norm = 0.0

                    # 谐波乘积谱（HPS）：真基频的 f,2f,3f,4f 都对应
                    # 频谱峰，而误锁候选（如 τ=3T/4）仅个别谐波对齐。
                    f0_cand = float(sr) / max(float(cand_tau_i), 1e-9)
                    hps_energy = 0.0
                    n_harm = 0
                    _f0_peak_energy = 0.0  # 候选基频处的谱能量（用于次谐波惩罚）
                    # 自适应搜索窗：FFT 分辨率粗（>20Hz/bin）时用 ±1 窗，
                    # 避免跨谐波污染；分辨率高时用 ±2 窗捕获频率微移。
                    bin_width = float(sr) / float(nfft)
                    half_win = 1 if bin_width > 20.0 else 2
                    for k in range(1, 5):
                        hf = f0_cand * float(k)
                        if hf >= sr * 0.48:
                            break
                        bin_idx = int(hf * float(nfft) / sr)
                        lo = max(0, bin_idx - half_win)
                        hi = min(n_bins - 1, bin_idx + half_win)
                        if lo < hi:
                            _peak = float(np.max(mag_spec[lo:hi + 1]))
                            hps_energy += _peak
                            n_harm += 1
                            if k == 1:
                                _f0_peak_energy = _peak
                    hps_norm = (hps_energy / max(n_harm, 1)) / max(mean_mag, 1e-12)

                    # 综合评分 = CMNDF + 自相关奖励 + HPS 奖励 + 长周期偏好 + 时序先验
                    cmndf_term = cmndf_val_i                    # 越低越好
                    ac_term = -ac_norm * 0.30                   # 越高越好→取负
                    # ── 高音区自适应 HPS 权重 ──
                    # 假声/头声 (>280Hz) 基频弱，CMNDF 谷浅不可靠；
                    # HPS 直接度量频谱谐波对齐度，对假声更稳健。
                    # 权重从 0.45 (低音) 平滑升至 0.65 (高音)。
                    _f0_for_weight = float(sr) / max(float(cand_tau_i), 1e-9)
                    if _f0_for_weight < 220.0:
                        _hps_weight = 0.45
                    elif _f0_for_weight < 280.0:
                        _hps_weight = 0.45 + 0.10 * (_f0_for_weight - 220.0) / 60.0
                    elif _f0_for_weight < 420.0:
                        _hps_weight = 0.55 + 0.10 * (_f0_for_weight - 280.0) / 140.0
                    else:
                        _hps_weight = 0.65  # >420Hz 强假声/头声，CMNDF 最不可靠
                    hps_term = -hps_norm * _hps_weight          # HPS越高越像真基频
                    tau_term = -(float(cand_tau_i) / float(tau_max)) * 0.15
                    # ── 低频谱峰惩罚：防止所有谐波误锁（3/2、4/3、2/1 等）──
                    # 原次谐波检查仅覆盖 f0/2（八度误锁），漏掉了：
                    #   τ=2T/3 → f0=1.5×真基频（D4→A4, 完全五度）
                    #   τ=3T/4 → f0=1.33×真基频（D4→G4, 完全四度）
                    # 通用方案：扫描 [f0×0.50, f0×0.90] 区间，若存在显著谱峰，
                    # 说明候选频率下方有更低的基频 → 候选是谐波 → 惩罚。
                    # 真基频下方无显著能量（最低检测频率以下）→ 不受惩罚。
                    _lower_peak_penalty = 0.0
                    _lower_lo_hz = f0_cand * 0.50
                    _lower_hi_hz = f0_cand * 0.90
                    _lower_lo_bin = int(_lower_lo_hz * float(nfft) / sr)
                    _lower_hi_bin = int(_lower_hi_hz * float(nfft) / sr)
                    _lower_lo_bin = max(2, _lower_lo_bin)
                    _lower_hi_bin = min(n_bins - 2, _lower_hi_bin)
                    if _lower_hi_bin > _lower_lo_bin + 2 and _f0_peak_energy > 0:
                        _lower_max_mag = float(np.max(mag_spec[_lower_lo_bin:_lower_hi_bin + 1]))
                        _lower_ratio = _lower_max_mag / max(_f0_peak_energy, 1e-12)
                        if _lower_ratio > 0.25:
                            # 下方有显著谱峰 → 此候选极可能是谐波
                            _lower_peak_penalty = min(_lower_ratio * 0.55, 0.60)
                    # ── 倒谱验证项 ──
                    # 真基频周期 τ=T 在倒谱中应有强峰；谐波候选（τ=3T/4 等）
                    # 在倒谱中则无对应峰（倒谱只反映真实周期）。
                    # 权重在高音区更高：CMNDF 越不可靠，倒谱越重要。
                    _cepst_val = float(_cepst_abs[int(cand_tau_i)]) if int(cand_tau_i) < len(_cepst_abs) else 0.0
                    _cepst_norm = _cepst_val / max(_cepst_max, 1e-12)
                    _cepst_weight = 0.35 if _f0_for_weight > 420.0 else (
                        0.12 if _f0_for_weight < 220.0 else (
                        0.12 + 0.23 * (_f0_for_weight - 220.0) / 200.0))
                    cepstral_term = -_cepst_norm * _cepst_weight  # 越高越好→取负
                    # 时序先验：接近前帧胜出者获得奖励（变化越小越可信）
                    # ═══════════════════════════════════════════════════════
                    # 关键：根据前帧质量调节先验权重，防止假声"错误锁定"正反馈。
                    # 假声基频弱 → CMNDF 高 → 前帧选择可能错误。
                    # 若前一帧是低质量选择，沿用强先验会把错误放大到当前帧，
                    # 形成 τ=3T/4 持续锁定的恶性循环。
                    #
                    # 质量门限:
                    #   prev_cmndf < 0.20 → full_prior (强周期性，可信)
                    #   prev_cmndf < 0.35 → half_prior (中等，减半防止错误传播)
                    #   prev_cmndf >=0.35 → zero_prior (假声弱基频，时序不可信)
                    # ═══════════════════════════════════════════════════════
                    _prev_quality = float(getattr(self, '_yin_prev_cmndf_quality', 0.0) or 0.0)
                    if _prev_quality < 0.20:
                        _prior_full, _prior_half = -0.40, -0.25
                    elif _prev_quality < 0.35:
                        _prior_full, _prior_half = -0.20, -0.12  # 减半
                    else:
                        _prior_full, _prior_half = 0.0, 0.0       # 零先验，全靠频谱
                    temporal_term = 0.0
                    if _prev_tau > 0:
                        tau_diff = abs(float(cand_tau_i) - _prev_tau) / max(_prev_tau, 1e-9)
                        if tau_diff < 0.04:
                            temporal_term = _prior_full  # ±4% 内
                        elif tau_diff < 0.08:
                            temporal_term = _prior_half  # ±8% 内
                    total = (cmndf_term + ac_term + hps_term + tau_term
                             + temporal_term + _lower_peak_penalty + cepstral_term)
                    scored.append((total, cand_tau_i))

                scored.sort(key=lambda x: x[0])
                cand_tau = scored[0][1]
                # ── 后选谐波子倍频验证 ──
                # HPS 综合评分后，验证胜出者是否可能是谐波（3/2、4/3、2/1）。
                # 若胜出者 f0 的 2/3、3/4、1/2 倍频处存在候选且得分接近，
                # 优先选择低频候选（真基频）。这对于 D4→A4 (3/2 误锁) 关键。
                _f0_winner = float(sr) / max(float(cand_tau), 1e-9)
                _best_score = scored[0][0]
                for _sub_ratio in (2.0 / 3.0, 3.0 / 4.0, 1.0 / 2.0):
                    _target_f0 = _f0_winner * _sub_ratio
                    if _target_f0 < ui_min_f:
                        continue
                    _target_tau = float(sr) / _target_f0
                    # 在前 6 名中寻找接近目标频率的候选
                    for _score_i, _tau_i in scored[:6]:
                        _cand_f0 = float(sr) / max(float(_tau_i), 1e-9)
                        if abs(_cand_f0 - _target_f0) / max(_target_f0, 1e-9) < 0.06:
                            # 子倍频候选得分与胜出者差距在 0.35 以内 → 优先低频
                            if _score_i - _best_score < 0.35:
                                cand_tau = int(_tau_i)
                            break
                    else:
                        continue
                    break
            elif len(candidates) == 1:
                cand_tau = candidates[0][0]
            else:
                # 没有任何候选：回退到全局 CMNDF 最小点
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
            # ── 存储本帧胜出周期 + 质量标记，供下一帧时序先验使用 ──
            self._yin_prev_tau_hat = float(tau_hat)
            # 记录本帧胜出者的 CMNDF 值，用于下一帧调节时序先验权重：
            #   cmndf < 0.20 → 高置信 → 全量时序先验
            #   cmndf < 0.35 → 中置信 → 减半时序先验（防止错误锁定）
            #   cmndf >=0.35 → 低置信 → 零时序先验（假声弱基频常见）
            #
            # ═══ 倒谱质量门（v9.5 关键修复） ═══
            # 假声谐波候选在 CMNDF 中常表现为深谷 [HI]（如 τ=3T/4），
            # 但倒谱在此 τ 处无峰。若直接存储原始 CMNDF [HI] 标记，
            # 下帧强时序先验会把谐波候选锁定，形成正反馈循环。
            # 门控：胜出者倒谱峰弱（< 最大峰的 35%）→ 人工提升
            # quality 到 ≥0.35（即 [LO]），确保下帧不使用强时序先验。
            _cmndf_quality = float(cmndf[cand_tau])
            _cepst_at_choice = float(_cepst_abs[int(cand_tau)]) if int(cand_tau) < len(_cepst_abs) else 0.0
            _cepst_ratio_at_choice = _cepst_at_choice / max(_cepst_max, 1e-12)
            if _cepst_ratio_at_choice < 0.30:
                # 倒谱不支持此候选 → 极可能是谐波误锁
                # 将质量标记强制提升到 ≥0.38 → 下帧时序先验归零
                _cmndf_quality = max(_cmndf_quality, 0.38)
            elif _cepst_ratio_at_choice < 0.50:
                # 倒谱支持偏弱 → 降至中等置信
                _cmndf_quality = max(_cmndf_quality, 0.25)
            self._yin_prev_cmndf_quality = _cmndf_quality
            # ── 诊断：每 40 帧输出（含候选质量信息）──
            if not hasattr(self, '_yin_diag_counter'):
                self._yin_diag_counter = 0
            self._yin_diag_counter += 1
            if self._yin_diag_counter % 40 == 0:
                n_cand = len(candidates)
                quality_tag = "HI" if cmndf[cand_tau] < 0.20 else ("MID" if cmndf[cand_tau] < 0.35 else "LO")
                print(f"[YIN-Diag] #{self._yin_diag_counter} nCand={n_cand} "
                      f"out={f0:.0f}Hz τ={tau_hat:.1f} cmndf={cmndf[cand_tau]:.3f}[{quality_tag}]")
            # 置信度：来自 CMNDF 谷深
            # cmndf 值近 0 → 强周期性 → 高置信；近 1 → 弱/无周期 → 低置信
            cmndf_val = float(cmndf[cand_tau])
            conf = float(np.clip(1.0 - cmndf_val, 0.0, 1.0))
            return f0, conf
        except Exception:
            return 0.0, 0.0
