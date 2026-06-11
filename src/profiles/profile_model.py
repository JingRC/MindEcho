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


# ── 练声训练统计 ──────────────────────────────────────────

@dataclass
class TrainingRecord:
    """一次练声的记录"""
    exercise_id: str = ""           # 练习 ID
    exercise_name: str = ""         # 练习名称
    exercise_category: str = ""     # 练习分类（warmup/intervals/agility/sustain/range）
    total_score: float = 0.0        # 总分 0-100
    level: str = "D"               # S/A/B/C/D
    pitch_accuracy: float = 0.0     # 音准分
    stability: float = 0.0          # 稳定分
    timing: float = 0.0             # 节奏分
    hold: float = 0.0               # 持续力
    perfect_count: int = 0
    great_count: int = 0
    good_count: int = 0
    ok_count: int = 0
    miss_count: int = 0
    max_streak: int = 0             # 最大连击
    tolerance_level: str = "intermediate"  # 容差等级
    duration_seconds: float = 0.0   # 本次练习用时（秒）
    avg_frame_hit_rate: float = 0.0  # 平均帧命中率 (0-1)
    avg_transition_time: float = 0.0  # 平均过渡耗时（秒）
    key_selected: str = "C"         # 选择的调性
    octave_shift: int = 0           # 八度偏移 -1/0/+1
    bpm: int = 100                  # 练习BPM
    range_low_midi: int = 0         # 本次练习最低音MIDI
    range_high_midi: int = 0        # 本次练习最高音MIDI
    date: str = ""                  # ISO 日期

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TrainingRecord":
        return cls(
            exercise_id=str(d.get("exercise_id", "") or ""),
            exercise_name=str(d.get("exercise_name", "") or ""),
            exercise_category=str(d.get("exercise_category", "") or ""),
            total_score=float(d.get("total_score", 0.0) or 0.0),
            level=str(d.get("level", "D") or "D"),
            pitch_accuracy=float(d.get("pitch_accuracy", 0.0) or 0.0),
            stability=float(d.get("stability", 0.0) or 0.0),
            timing=float(d.get("timing", 0.0) or 0.0),
            hold=float(d.get("hold", 0.0) or 0.0),
            perfect_count=int(d.get("perfect_count", 0) or 0),
            great_count=int(d.get("great_count", 0) or 0),
            good_count=int(d.get("good_count", 0) or 0),
            ok_count=int(d.get("ok_count", 0) or 0),
            miss_count=int(d.get("miss_count", 0) or 0),
            max_streak=int(d.get("max_streak", 0) or 0),
            tolerance_level=str(d.get("tolerance_level", "intermediate") or "intermediate"),
            duration_seconds=float(d.get("duration_seconds", 0.0) or 0.0),
            avg_frame_hit_rate=float(d.get("avg_frame_hit_rate", 0.0) or 0.0),
            avg_transition_time=float(d.get("avg_transition_time", 0.0) or 0.0),
            key_selected=str(d.get("key_selected", "C") or "C"),
            octave_shift=int(d.get("octave_shift", 0) or 0),
            bpm=int(d.get("bpm", 100) or 100),
            range_low_midi=int(d.get("range_low_midi", 0) or 0),
            range_high_midi=int(d.get("range_high_midi", 0) or 0),
            date=str(d.get("date", "") or ""),
        )


@dataclass
class TrainingStats:
    """练声训练聚合统计"""
    total_sessions: int = 0
    total_minutes: float = 0.0
    average_score: float = 0.0       # EMA 平均
    best_score: float = 0.0
    best_exercise: str = ""
    level: str = "beginner"          # beginner / intermediate / advanced / expert
    level_progress: float = 0.0      # 0-1 当前等级进度
    recent_records: List[TrainingRecord] = field(default_factory=list)  # 最近 50 条
    vocal_range_low_midi: int = 0    # 练声中测得的低音
    vocal_range_high_midi: int = 0   # 练声中测得的高音
    _ema_alpha: float = field(default=0.15, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_sessions": self.total_sessions,
            "total_minutes": round(self.total_minutes, 1),
            "average_score": round(self.average_score, 1),
            "best_score": round(self.best_score, 1),
            "best_exercise": self.best_exercise,
            "level": self.level,
            "level_progress": round(self.level_progress, 3),
            "recent_records": [r.to_dict() for r in self.recent_records[-50:]],
            "vocal_range_low_midi": self.vocal_range_low_midi,
            "vocal_range_high_midi": self.vocal_range_high_midi,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TrainingStats":
        records = []
        for rd in (d.get("recent_records", []) or []):
            try:
                records.append(TrainingRecord.from_dict(rd))
            except Exception:
                pass
        return cls(
            total_sessions=int(d.get("total_sessions", 0) or 0),
            total_minutes=float(d.get("total_minutes", 0.0) or 0.0),
            average_score=float(d.get("average_score", 0.0) or 0.0),
            best_score=float(d.get("best_score", 0.0) or 0.0),
            best_exercise=str(d.get("best_exercise", "") or ""),
            level=str(d.get("level", "beginner") or "beginner"),
            level_progress=float(d.get("level_progress", 0.0) or 0.0),
            recent_records=records,
            vocal_range_low_midi=int(d.get("vocal_range_low_midi", 0) or 0),
            vocal_range_high_midi=int(d.get("vocal_range_high_midi", 0) or 0),
        )

    def add_record(self, record: TrainingRecord) -> None:
        """添加一条训练记录并更新聚合统计。"""
        self.total_sessions += 1
        # 累加练声时长（秒 → 分钟）
        self.total_minutes += record.duration_seconds / 60.0
        self.recent_records.append(record)
        if len(self.recent_records) > 50:
            self.recent_records = self.recent_records[-50:]

        # EMA 更新平均分
        if self.average_score == 0:
            self.average_score = record.total_score
        else:
            self.average_score = (
                self._ema_alpha * record.total_score
                + (1 - self._ema_alpha) * self.average_score
            )

        # 最佳分
        if record.total_score > self.best_score:
            self.best_score = record.total_score
            self.best_exercise = record.exercise_name

        # 更新练声中测得的音域
        if record.range_low_midi > 0:
            if self.vocal_range_low_midi <= 0 or record.range_low_midi < self.vocal_range_low_midi:
                self.vocal_range_low_midi = record.range_low_midi
        if record.range_high_midi > 0:
            if record.range_high_midi > self.vocal_range_high_midi:
                self.vocal_range_high_midi = record.range_high_midi

        # 等级晋升检查
        self._update_level()

    # ── 等级晋升 ──────────────────────────────────────

    _LEVEL_THRESHOLDS = [
        ("expert",       93.0, 200),   # 天籁之音: >93分 + ≥200次
        ("advanced",     88.0, 100),   # 实力唱将: >88分 + ≥100次
        ("intermediate", 80.0, 50),    # 渐入佳境: >80分 + ≥50次
        ("beginner",      0.0, 0),     # 初出茅庐: 默认
    ]

    def _update_level(self) -> None:
        """根据平均分和练习次数判断等级。"""
        for lvl_name, score_thr, session_thr in self._LEVEL_THRESHOLDS:
            if (self.average_score >= score_thr
                    and self.total_sessions >= session_thr):
                if self.level != lvl_name:
                    self.level = lvl_name
                break

        # 计算当前等级进度 (到下一级的百分比)
        levels = ["beginner", "intermediate", "advanced", "expert"]
        try:
            cur_idx = levels.index(self.level)
            if cur_idx < len(levels) - 1:
                next_name = levels[cur_idx + 1]
                for lvl_name, score_thr, session_thr in self._LEVEL_THRESHOLDS:
                    if lvl_name == next_name:
                        score_progress = min(1.0, self.average_score / max(score_thr, 1))
                        session_progress = min(1.0, self.total_sessions / max(session_thr, 1))
                        self.level_progress = (score_progress + session_progress) / 2.0
                        break
            else:
                self.level_progress = 1.0
        except (ValueError, IndexError):
            self.level_progress = 0.0


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
    training_stats: TrainingStats = field(default_factory=TrainingStats)
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
            "training_stats": self.training_stats.to_dict(),
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
            training_stats=TrainingStats.from_dict(d.get("training_stats", {}) or {}),
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
