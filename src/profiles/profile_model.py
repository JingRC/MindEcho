"""SingerProfile 数据模型 —— 歌手个性化存档

每个存档对应一位歌手，包含：
- 基本信息（名称、声部、性别）
- 换声点数据（手动校准 / 自适应估计）
- 音域统计（P5-P95 百分位）
- 音色指纹（spectral_tilt, hm_over_hh, mid_high_ratio 均值）
- 使用统计（累计时长、技巧分布）

数据持久化到 profiles/<名称>/profile.json
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any


PROFILE_VERSION = 1


# ── 换声点数据 ──────────────────────────────────────────────

@dataclass
class PassaggioData:
    """换声点 (secondo passaggio) 的估计值及来源"""
    t4_hz: float = 0.0                     # 第二换声点频率 (Hz)
    source: str = "default"                # "calibrated" | "auto_estimated" | "default"
    confidence: float = 0.0                # 0.0 ~ 1.0，数据越多/校准越精确则越高
    last_calibrated: str = ""              # ISO 日期 "2026-06-03"
    auto_estimated_t4: float = 0.0         # 纯自动估计值（即使手动校准后仍追踪）
    calibration_scan_file: str = ""        # 校准扫描数据文件路径（相对 profile 目录）

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PassaggioData":
        return cls(
            t4_hz=float(d.get("t4_hz", 0.0) or 0.0),
            source=str(d.get("source", "default") or "default"),
            confidence=float(d.get("confidence", 0.0) or 0.0),
            last_calibrated=str(d.get("last_calibrated", "") or ""),
            auto_estimated_t4=float(d.get("auto_estimated_t4", 0.0) or 0.0),
            calibration_scan_file=str(d.get("calibration_scan_file", "") or ""),
        )


# ── 音域统计 ────────────────────────────────────────────────

@dataclass
class PitchStats:
    """歌手音域百分位统计（只统计 voiced 帧，置信度 ≥ 0.34）"""
    p5_hz: float = 0.0
    p25_hz: float = 0.0
    p50_hz: float = 0.0      # 中位音高 ≈ tessitura 中心
    p75_hz: float = 0.0
    p85_hz: float = 0.0      # 常用音域上界（用于估计 passaggio）
    p95_hz: float = 0.0      # 音域上界
    min_hz: float = 0.0
    max_hz: float = 0.0
    total_voiced_frames: int = 0       # 累计发声帧数
    session_count: int = 0             # 累计录音次数

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PitchStats":
        return cls(
            p5_hz=float(d.get("p5_hz", 0.0) or 0.0),
            p25_hz=float(d.get("p25_hz", 0.0) or 0.0),
            p50_hz=float(d.get("p50_hz", 0.0) or 0.0),
            p75_hz=float(d.get("p75_hz", 0.0) or 0.0),
            p85_hz=float(d.get("p85_hz", 0.0) or 0.0),
            p95_hz=float(d.get("p95_hz", 0.0) or 0.0),
            min_hz=float(d.get("min_hz", 0.0) or 0.0),
            max_hz=float(d.get("max_hz", 0.0) or 0.0),
            total_voiced_frames=int(d.get("total_voiced_frames", 0) or 0),
            session_count=int(d.get("session_count", 0) or 0),
        )

    def update_from_frequencies(self, frequencies_hz: List[float]) -> None:
        """用一批音高数据更新百分位统计（在线 Welford 式增量更新）"""
        if not frequencies_hz:
            return
        freqs = [f for f in frequencies_hz if f > 0.0]
        if not freqs:
            return
        n_new = len(freqs)
        n_old = self.total_voiced_frames
        n_total = n_old + n_new

        # 简单加权合并：用旧百分位近似 + 新数据排序
        # P50/P85/P95 用分桶近似，避免存储全部历史
        if n_old == 0:
            sorted_all = sorted(freqs)
        else:
            # 用旧百分位重建近似分布（粗糙但够用）
            old_sorted = []
            if self.min_hz > 0:
                old_sorted = _approx_distribution_from_percentiles(self, n_old)
            sorted_all = sorted(old_sorted + freqs)

        n = len(sorted_all)
        self.min_hz = sorted_all[0]
        self.max_hz = sorted_all[-1]
        self.p5_hz = sorted_all[int(n * 0.05)]
        self.p25_hz = sorted_all[int(n * 0.25)]
        self.p50_hz = sorted_all[int(n * 0.50)]
        self.p75_hz = sorted_all[int(n * 0.75)]
        self.p85_hz = sorted_all[int(n * 0.85)]
        self.p95_hz = sorted_all[int(n * 0.95)]
        self.total_voiced_frames = n_total
        self.session_count += 1


def _approx_distribution_from_percentiles(stats: PitchStats, n: int) -> List[float]:
    """从百分位近似重建分布（用于增量合并）"""
    if n <= 0 or stats.min_hz <= 0:
        return []
    points = []
    percentiles = [
        (0.0, stats.min_hz),
        (0.05, stats.p5_hz),
        (0.25, stats.p25_hz),
        (0.50, stats.p50_hz),
        (0.75, stats.p75_hz),
        (0.85, stats.p85_hz),
        (0.95, stats.p95_hz),
        (1.0, stats.max_hz),
    ]
    for i in range(len(percentiles) - 1):
        p_lo, v_lo = percentiles[i]
        p_hi, v_hi = percentiles[i + 1]
        count = int(n * (p_hi - p_lo))
        if count > 0 and v_lo > 0 and v_hi > 0:
            step = (v_hi - v_lo) / count
            for j in range(count):
                points.append(v_lo + step * j)
    return points


# ── 音色指纹 ────────────────────────────────────────────────

@dataclass
class TimbreFingerprint:
    """歌手典型音色特征（长期 EMA 均值）"""
    avg_spectral_tilt: float = 0.0
    avg_hm_over_hh: float = 0.0
    avg_mid_high_ratio: float = 0.0
    avg_zcr: float = 0.0
    avg_rms: float = 0.0
    fhe_hz: float = 0.0                 # 半能量频率 (Frequency of Half Energy)
    spectral_centroid_hz: float = 0.0   # 频谱质心
    timbre_quality: float = 0.0          # 音色质量评分
    sample_count: int = 0
    _ema_alpha: float = field(default=0.02, repr=False)  # 慢速 EMA 用于长期指纹

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TimbreFingerprint":
        return cls(
            avg_spectral_tilt=float(d.get("avg_spectral_tilt", 0.0) or 0.0),
            avg_hm_over_hh=float(d.get("avg_hm_over_hh", 0.0) or 0.0),
            avg_mid_high_ratio=float(d.get("avg_mid_high_ratio", 0.0) or 0.0),
            avg_zcr=float(d.get("avg_zcr", 0.0) or 0.0),
            avg_rms=float(d.get("avg_rms", 0.0) or 0.0),
            fhe_hz=float(d.get("fhe_hz", 0.0) or 0.0),
            spectral_centroid_hz=float(d.get("spectral_centroid_hz", 0.0) or 0.0),
            timbre_quality=float(d.get("timbre_quality", 0.0) or 0.0),
            sample_count=int(d.get("sample_count", 0) or 0),
        )

    def update(
        self,
        spectral_tilt: float,
        hm_over_hh: float,
        mid_high_ratio: float,
        zcr: float = 0.0,
        rms: float = 0.0,
    ) -> None:
        """EMA 更新音色指纹"""
        a = self._ema_alpha
        if self.sample_count == 0:
            self.avg_spectral_tilt = spectral_tilt
            self.avg_hm_over_hh = hm_over_hh
            self.avg_mid_high_ratio = mid_high_ratio
            self.avg_zcr = zcr
            self.avg_rms = rms
        else:
            self.avg_spectral_tilt = a * spectral_tilt + (1 - a) * self.avg_spectral_tilt
            self.avg_hm_over_hh = a * hm_over_hh + (1 - a) * self.avg_hm_over_hh
            self.avg_mid_high_ratio = a * mid_high_ratio + (1 - a) * self.avg_mid_high_ratio
            self.avg_zcr = a * zcr + (1 - a) * self.avg_zcr
            self.avg_rms = a * rms + (1 - a) * self.avg_rms
        self.sample_count += 1


# ── 使用统计 ────────────────────────────────────────────────

@dataclass
class UsageStats:
    """使用统计"""
    total_sessions: int = 0
    total_minutes: float = 0.0
    last_active: str = ""
    technique_distribution: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "UsageStats":
        return cls(
            total_sessions=int(d.get("total_sessions", 0) or 0),
            total_minutes=float(d.get("total_minutes", 0.0) or 0.0),
            last_active=str(d.get("last_active", "") or ""),
            technique_distribution=dict(d.get("technique_distribution", {}) or {}),
        )


# ── 主存档数据类 ─────────────────────────────────────────────

@dataclass
class SingerProfile:
    """歌手个性化存档

    一个存档 = 一个 profiles/<name>/ 文件夹
    包含 profile.json + recordings/ 子目录
    """
    id: str = ""                           # UUID
    name: str = ""                         # 显示名称（如"张三"）
    voice_type_manual: str = ""            # 手动选择的声部 "baritone"/""=不指定
    voice_type_inferred: str = ""          # 自适应推断的声部
    gender_manual: str = ""                # "male" / "female" / ""
    gender_inferred: str = ""              # 模型自动检测的性别
    passaggio: PassaggioData = field(default_factory=PassaggioData)
    pitch_stats: PitchStats = field(default_factory=PitchStats)
    timbre: TimbreFingerprint = field(default_factory=TimbreFingerprint)
    usage: UsageStats = field(default_factory=UsageStats)
    created_at: str = ""
    updated_at: str = ""

    # ── 工厂方法 ──────────────────────────────────────────

    @classmethod
    def create_new(
        cls,
        name: str,
        voice_type: str = "",
        gender: str = "",
    ) -> "SingerProfile":
        """创建新存档"""
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        return cls(
            id=str(uuid.uuid4())[:12],
            name=name.strip(),
            voice_type_manual=voice_type,
            gender_manual=gender,
            created_at=now,
            updated_at=now,
        )

    # ── 属性 ──────────────────────────────────────────────

    @property
    def folder_name(self) -> str:
        """存档文件夹名 = <name>"""
        return self.name if self.name else f"unnamed_{self.id}"

    @property
    def effective_gender(self) -> str:
        """获取有效性别（手动 > 推断 > 空）"""
        return self.gender_manual or self.gender_inferred or ""

    @property
    def effective_voice_type(self) -> str:
        """获取有效声部（手动 > 推断 > 空 = 不指定）"""
        return self.voice_type_manual or self.voice_type_inferred or ""

    @property
    def is_female(self) -> bool:
        """是否为女声"""
        g = self.effective_gender.lower()
        return g in ("female", "女") or self.effective_voice_type.lower() in _FEMALE_VOICE_TYPES

    @property
    def is_guest(self) -> bool:
        """是否为访客模式（无存档）"""
        return not bool(self.id or self.name)

    # ── 序列化 ────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": PROFILE_VERSION,
            "id": self.id,
            "name": self.name,
            "voice_type_manual": self.voice_type_manual,
            "voice_type_inferred": self.voice_type_inferred,
            "gender_manual": self.gender_manual,
            "gender_inferred": self.gender_inferred,
            "passaggio": self.passaggio.to_dict(),
            "pitch_stats": self.pitch_stats.to_dict(),
            "timbre": self.timbre.to_dict(),
            "usage": self.usage.to_dict(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SingerProfile":
        return cls(
            id=str(d.get("id", "") or ""),
            name=str(d.get("name", "") or ""),
            voice_type_manual=str(d.get("voice_type_manual", "") or ""),
            voice_type_inferred=str(d.get("voice_type_inferred", "") or ""),
            gender_manual=str(d.get("gender_manual", "") or ""),
            gender_inferred=str(d.get("gender_inferred", "") or ""),
            passaggio=PassaggioData.from_dict(d.get("passaggio", {}) or {}),
            pitch_stats=PitchStats.from_dict(d.get("pitch_stats", {}) or {}),
            timbre=TimbreFingerprint.from_dict(d.get("timbre", {}) or {}),
            usage=UsageStats.from_dict(d.get("usage", {}) or {}),
            created_at=str(d.get("created_at", "") or ""),
            updated_at=str(d.get("updated_at", "") or ""),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "SingerProfile":
        return cls.from_dict(json.loads(json_str))


# 女声声部集合（与 integrated_recording_interface 中一致）
_FEMALE_VOICE_TYPES = frozenset({"soprano", "mezzo_soprano", "contralto"})
