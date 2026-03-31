from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence
import math

import numpy as np


@dataclass
class OfflineVibratoConfig:
    min_duration_s: float = 0.26
    max_gap_s: float = 0.085
    baseline_window_s: float = 0.24
    envelope_window_s: float = 0.12
    min_rate_hz: float = 3.0
    max_rate_hz: float = 8.8
    min_depth_cents: float = 10.0
    max_depth_cents: float = 180.0
    min_cycles: int = 3
    merge_gap_s: float = 0.10


@dataclass
class OfflineVibratoRegion:
    start_time: float
    end_time: float
    center_time: float
    duration: float
    rate_hz: float
    depth_cents: float
    depth_hz: float
    confidence: float
    strength: float
    regularity_score: float
    stability_score: float
    base_pitch_hz: float
    debug_payload: Dict[str, Any] = field(default_factory=dict)


class OfflineTechniqueAnalysisService:
    def __init__(self, config: Optional[OfflineVibratoConfig] = None):
        self.config = config or OfflineVibratoConfig()

    def detect_vibrato(self, frames: Sequence[Any]) -> List[OfflineVibratoRegion]:
        normalized = self._normalize_frames(frames)
        if len(normalized) < 8:
            return []
        segments = self._collect_voiced_segments(normalized)
        regions: List[OfflineVibratoRegion] = []
        for segment in segments:
            if len(segment) < 8:
                continue
            regions.extend(self._detect_vibrato_in_segment(segment))
        return self._merge_regions(regions)

    def _normalize_frames(self, frames: Sequence[Any]) -> List[Dict[str, float]]:
        normalized: List[Dict[str, float]] = []
        for item in list(frames or []):
            try:
                preview_only = bool(getattr(item, 'preview_only', False))
            except Exception:
                preview_only = False
            if preview_only:
                continue
            try:
                has_pitch = bool(getattr(item, 'has_pitch', False))
                time_val = float(getattr(item, 'timeline_time', 0.0) or 0.0)
                freq_val = float(getattr(item, 'detected_frequency_hz', 0.0) or 0.0)
                conf_val = float(getattr(item, 'confidence', 0.0) or 0.0)
                rms_val = float(getattr(item, 'audio_rms', 0.0) or 0.0)
            except Exception:
                continue
            if time_val < 0.0:
                continue
            normalized.append({
                'time': time_val,
                'frequency': freq_val,
                'confidence': conf_val,
                'audio_rms': rms_val,
                'has_pitch': 1.0 if (has_pitch and freq_val > 0.0) else 0.0,
            })
        normalized.sort(key=lambda item: item['time'])
        return normalized

    def _collect_voiced_segments(self, frames: Sequence[Dict[str, float]]) -> List[List[Dict[str, float]]]:
        segments: List[List[Dict[str, float]]] = []
        current: List[Dict[str, float]] = []
        cfg = self.config
        prev_time: Optional[float] = None
        for frame in frames:
            if frame['has_pitch'] < 0.5:
                if current:
                    segments.append(current)
                    current = []
                prev_time = None
                continue
            if prev_time is not None and (frame['time'] - prev_time) > cfg.max_gap_s:
                if current:
                    segments.append(current)
                current = []
            current.append(frame)
            prev_time = frame['time']
        if current:
            segments.append(current)
        return segments

    def _detect_vibrato_in_segment(self, segment: Sequence[Dict[str, float]]) -> List[OfflineVibratoRegion]:
        cfg = self.config
        times = np.asarray([item['time'] for item in segment], dtype=np.float64)
        freqs = np.asarray([max(item['frequency'], 1e-9) for item in segment], dtype=np.float64)
        confidences = np.asarray([item['confidence'] for item in segment], dtype=np.float64)
        if times.size < 8:
            return []
        dt = np.diff(times)
        valid_dt = dt[(dt > 1e-5) & np.isfinite(dt)]
        if valid_dt.size == 0:
            return []
        sample_dt = float(np.median(valid_dt))
        if sample_dt <= 1e-5:
            return []
        fps = 1.0 / sample_dt
        baseline_window = self._window_samples(cfg.baseline_window_s, fps, minimum=7)
        envelope_window = self._window_samples(cfg.envelope_window_s, fps, minimum=5)

        log_freq = np.log2(freqs)
        baseline = self._moving_average(log_freq, baseline_window)
        residual_cents = (log_freq - baseline) * 1200.0
        residual_cents = self._moving_average(residual_cents, 3)
        envelope = self._moving_average(np.abs(residual_cents), envelope_window)
        active_mask = envelope >= max(4.0, cfg.min_depth_cents * 0.55)

        runs = self._mask_runs(active_mask)
        regions: List[OfflineVibratoRegion] = []
        for start_idx, end_idx in runs:
            if (end_idx - start_idx) < 6:
                continue
            run_times = times[start_idx:end_idx]
            run_residual = residual_cents[start_idx:end_idx]
            run_freqs = freqs[start_idx:end_idx]
            run_conf = confidences[start_idx:end_idx]
            duration = float(run_times[-1] - run_times[0]) if run_times.size >= 2 else 0.0
            if duration < cfg.min_duration_s:
                continue
            deadband = max(2.5, cfg.min_depth_cents * 0.30)
            zero_crossings = self._zero_crossings(run_residual, deadband)
            cycle_count = zero_crossings // 2
            if cycle_count < cfg.min_cycles:
                continue
            rate_hz = float(zero_crossings / max(duration * 2.0, 1e-6))
            depth_cents = float(np.percentile(np.abs(run_residual), 88))
            if not (cfg.min_rate_hz <= rate_hz <= cfg.max_rate_hz):
                continue
            if not (cfg.min_depth_cents <= depth_cents <= cfg.max_depth_cents):
                continue
            regularity = self._regularity_score(run_residual, sample_dt, deadband)
            stability = self._stability_score(run_conf, run_freqs)
            symmetry = self._symmetry_score(run_residual, deadband)
            trend_ratio = self._trend_ratio(run_times, run_residual)
            if regularity < 0.30 or stability < 0.24:
                continue
            if symmetry < 0.24 or trend_ratio > 0.42:
                continue
            base_pitch_hz = float(np.exp2(np.mean(log_freq[start_idx:end_idx])))
            depth_hz = float(base_pitch_hz * (2 ** (depth_cents / 1200.0) - 1.0))
            confidence = self._confidence_score(rate_hz, depth_cents, regularity, stability, symmetry, duration)
            strength = self._strength_score(depth_cents, regularity, stability, symmetry)
            regions.append(OfflineVibratoRegion(
                start_time=float(run_times[0]),
                end_time=float(run_times[-1]),
                center_time=0.5 * float(run_times[0] + run_times[-1]),
                duration=duration,
                rate_hz=rate_hz,
                depth_cents=depth_cents,
                depth_hz=depth_hz,
                confidence=confidence,
                strength=strength,
                regularity_score=regularity,
                stability_score=stability,
                base_pitch_hz=base_pitch_hz,
                debug_payload={
                    'zero_crossings': int(zero_crossings),
                    'cycle_count': int(cycle_count),
                    'sample_dt': sample_dt,
                    'fps': fps,
                    'baseline_window': int(baseline_window),
                    'envelope_window': int(envelope_window),
                    'symmetry_score': float(symmetry),
                    'trend_ratio': float(trend_ratio),
                    'mean_confidence': float(np.mean(run_conf)) if run_conf.size else 0.0,
                    'residual_peak_cents': float(np.max(np.abs(run_residual))) if run_residual.size else 0.0,
                },
            ))
        return regions

    def _merge_regions(self, regions: Iterable[OfflineVibratoRegion]) -> List[OfflineVibratoRegion]:
        cfg = self.config
        ordered = sorted(list(regions), key=lambda item: (item.start_time, item.end_time))
        merged: List[OfflineVibratoRegion] = []
        for region in ordered:
            if not merged:
                merged.append(region)
                continue
            prev = merged[-1]
            gap = float(region.start_time) - float(prev.end_time)
            if gap > cfg.merge_gap_s:
                merged.append(region)
                continue
            if abs(float(region.rate_hz) - float(prev.rate_hz)) > 1.6:
                merged.append(region)
                continue
            total_duration = max(float(region.end_time), float(prev.end_time)) - min(float(region.start_time), float(prev.start_time))
            if total_duration <= 0.0:
                continue
            prev.end_time = max(float(prev.end_time), float(region.end_time))
            prev.start_time = min(float(prev.start_time), float(region.start_time))
            prev.center_time = 0.5 * (prev.start_time + prev.end_time)
            prev.duration = total_duration
            prev.rate_hz = 0.5 * (float(prev.rate_hz) + float(region.rate_hz))
            prev.depth_cents = max(float(prev.depth_cents), float(region.depth_cents))
            prev.depth_hz = max(float(prev.depth_hz), float(region.depth_hz))
            prev.confidence = max(float(prev.confidence), float(region.confidence))
            prev.strength = max(float(prev.strength), float(region.strength))
            prev.regularity_score = max(float(prev.regularity_score), float(region.regularity_score))
            prev.stability_score = max(float(prev.stability_score), float(region.stability_score))
            prev.base_pitch_hz = float((prev.base_pitch_hz + region.base_pitch_hz) * 0.5)
            prev.debug_payload = {
                **dict(prev.debug_payload or {}),
                **dict(region.debug_payload or {}),
                'merged': True,
            }
        return merged

    def _window_samples(self, window_s: float, fps: float, minimum: int) -> int:
        samples = max(minimum, int(round(float(window_s) * max(float(fps), 1.0))))
        if samples % 2 == 0:
            samples += 1
        return samples

    def _moving_average(self, values: np.ndarray, window: int) -> np.ndarray:
        if values.size == 0 or window <= 1:
            return values.copy()
        kernel = np.ones(int(window), dtype=np.float64) / float(window)
        padded = np.pad(values, (window // 2, window // 2), mode='edge')
        smoothed = np.convolve(padded, kernel, mode='valid')
        return smoothed[:values.size]

    def _mask_runs(self, mask: np.ndarray) -> List[tuple[int, int]]:
        runs: List[tuple[int, int]] = []
        start: Optional[int] = None
        for idx, active in enumerate(mask.tolist()):
            if active and start is None:
                start = idx
            elif (not active) and start is not None:
                runs.append((start, idx))
                start = None
        if start is not None:
            runs.append((start, int(mask.size)))
        return runs

    def _zero_crossings(self, values: np.ndarray, deadband: float) -> int:
        if values.size < 3:
            return 0
        signs = np.zeros(values.size, dtype=np.int8)
        signs[values >= deadband] = 1
        signs[values <= -deadband] = -1
        compressed: List[int] = []
        for sign in signs.tolist():
            if sign == 0:
                continue
            if not compressed or compressed[-1] != sign:
                compressed.append(sign)
        return max(0, len(compressed) - 1)

    def _regularity_score(self, residual_cents: np.ndarray, sample_dt: float, deadband: float) -> float:
        if residual_cents.size < 6:
            return 0.0
        signs = np.zeros(residual_cents.size, dtype=np.int8)
        signs[residual_cents >= deadband] = 1
        signs[residual_cents <= -deadband] = -1
        change_indices: List[int] = []
        prev = 0
        for idx, sign in enumerate(signs.tolist()):
            if sign == 0:
                continue
            if prev != 0 and sign != prev:
                change_indices.append(idx)
            prev = sign
        if len(change_indices) < 3:
            return 0.0
        intervals = np.diff(np.asarray(change_indices, dtype=np.float64)) * max(sample_dt, 1e-6)
        if intervals.size == 0:
            return 0.0
        mean_interval = float(np.mean(intervals))
        if mean_interval <= 1e-6:
            return 0.0
        ratio = float(np.std(intervals) / mean_interval)
        return max(0.0, min(1.0, 1.0 - ratio / 0.55))

    def _stability_score(self, confidences: np.ndarray, freqs: np.ndarray) -> float:
        if confidences.size == 0 or freqs.size == 0:
            return 0.0
        mean_conf = float(np.mean(np.clip(confidences, 0.0, 1.0)))
        if freqs.size < 2:
            return mean_conf
        diff = np.diff(np.log2(np.clip(freqs, 1e-9, None))) * 1200.0
        jitter = float(np.std(diff)) if diff.size else 0.0
        jitter_term = max(0.0, min(1.0, 1.0 - jitter / 35.0))
        return max(0.0, min(1.0, mean_conf * 0.62 + jitter_term * 0.38))

    def _symmetry_score(self, residual_cents: np.ndarray, deadband: float) -> float:
        if residual_cents.size < 6:
            return 0.0
        pos = residual_cents[residual_cents >= deadband]
        neg = -residual_cents[residual_cents <= -deadband]
        if pos.size == 0 or neg.size == 0:
            return 0.0
        pos_peak = float(np.percentile(pos, 80)) if pos.size else 0.0
        neg_peak = float(np.percentile(neg, 80)) if neg.size else 0.0
        peak_balance = min(pos_peak, neg_peak) / max(max(pos_peak, neg_peak), 1e-6)
        coverage_balance = min(float(pos.size), float(neg.size)) / max(float(pos.size), float(neg.size), 1.0)
        return max(0.0, min(1.0, peak_balance * 0.62 + coverage_balance * 0.38))

    def _trend_ratio(self, times: np.ndarray, residual_cents: np.ndarray) -> float:
        if times.size < 6 or residual_cents.size < 6:
            return 1.0
        span = float(times[-1] - times[0]) if times.size >= 2 else 0.0
        peak_to_peak = float(np.ptp(residual_cents)) if residual_cents.size else 0.0
        if span <= 1e-6 or peak_to_peak <= 1e-6:
            return 1.0
        centered_t = times - float(np.mean(times))
        centered_r = residual_cents - float(np.mean(residual_cents))
        denom = float(np.dot(centered_t, centered_t))
        if denom <= 1e-9:
            return 1.0
        slope = float(np.dot(centered_t, centered_r) / denom)
        drift = abs(slope) * span
        return max(0.0, drift / max(peak_to_peak, 1e-6))

    def _confidence_score(self, rate_hz: float, depth_cents: float, regularity: float, stability: float, symmetry: float, duration: float) -> float:
        cfg = self.config
        rate_mid = 5.6
        rate_span = max(rate_mid - cfg.min_rate_hz, cfg.max_rate_hz - rate_mid, 1.0)
        rate_score = max(0.0, 1.0 - abs(rate_hz - rate_mid) / rate_span)
        depth_mid = 45.0
        depth_span = max(depth_mid - cfg.min_depth_cents, cfg.max_depth_cents - depth_mid, 1.0)
        depth_score = max(0.0, 1.0 - abs(depth_cents - depth_mid) / depth_span)
        duration_score = max(0.0, min(1.0, duration / 0.55))
        score = rate_score * 0.24 + depth_score * 0.18 + regularity * 0.22 + stability * 0.16 + symmetry * 0.12 + duration_score * 0.08
        return max(0.0, min(0.96, score))

    def _strength_score(self, depth_cents: float, regularity: float, stability: float, symmetry: float) -> float:
        depth_term = max(0.0, min(1.0, depth_cents / 80.0))
        return max(0.0, min(0.95, depth_term * 0.44 + regularity * 0.24 + stability * 0.18 + symmetry * 0.14))