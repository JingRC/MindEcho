"""上下文构建器 —— 将 MindEcho 音高数据/技巧事件转化为 LLM 可读的结构化摘要"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np


# ═══════════════════════════════════════════════════════════════
# 上下文数据结构
# ═══════════════════════════════════════════════════════════════


@dataclass
class PitchStats:
    """音准统计摘要"""
    total_frames: int
    voiced_frames: int
    pitch_accuracy: float          # 整体音准命中率 (0-1)
    mean_cent_deviation: float     # 平均音分偏差
    std_cent_deviation: float      # 音分偏差标准差
    sharp_ratio: float             # 偏高比例
    flat_ratio: float              # 偏低比例
    min_freq: float                # 最低频率
    max_freq: float                # 最高频率
    mean_confidence: float         # 平均置信度


@dataclass
class TechniqueSummary:
    """技巧事件摘要"""
    vibrato_count: int = 0
    vibrato_avg_rate: float = 0.0
    vibrato_avg_depth: float = 0.0
    slide_count: int = 0
    breath_count: int = 0
    register_transition_count: int = 0
    breathiness_score: float = 0.0
    voice_type_distribution: dict[str, float] = None  # chest/falsetto/mix ratio

    def __post_init__(self):
        if self.voice_type_distribution is None:
            self.voice_type_distribution = {}


@dataclass
class SegmentAnalysis:
    """分段分析"""
    start_time: float
    end_time: float
    label: str                     # "verse 1", "chorus", "bridge" 等
    accuracy: float
    issues: list[str]


@dataclass
class SingingContext:
    """一次完整演唱的结构化上下文"""
    # L1: 整体统计 (~200 tokens)
    stats: Optional[PitchStats] = None

    # L2: 分段描述 (~500 tokens)
    segments: list[SegmentAnalysis] = None

    # 技巧摘要
    techniques: TechniqueSummary = None

    # 对比结果 (如果有专业参考)
    comparison: Optional["ComparisonResult"] = None

    # L2 增强特征（v2 — 从 technique_events / pitch_data 中提取）
    breath_analysis: Optional[str] = None      # 换气分析表格 + 问题标注
    segment_stability: Optional[str] = None    # 逐段稳定性报告
    pitch_drift: Optional[str] = None          # 音高漂移趋势

    @property
    def has_valid_singing(self) -> bool:
        """是否检测到有效人声（置信度筛选后有足够多的有声帧）"""
        if self.stats is None:
            return False
        if self.stats.total_frames == 0:
            return False
        voiced_ratio = self.stats.voiced_frames / self.stats.total_frames
        return voiced_ratio >= 0.10

    def __post_init__(self):
        if self.segments is None:
            self.segments = []
        if self.techniques is None:
            self.techniques = TechniqueSummary()


@dataclass
class ComparisonResult:
    """与专业歌手对比的结果"""
    reference_name: str = ""
    overall_accuracy_gap: float = 0.0    # 综合音准差距 (平均音分)
    dtw_aligned_points: int = 0
    best_segment: str = ""               # 表现最好的段落
    worst_segment: str = ""              # 最需改进的段落
    strengths: list[str] = None
    weaknesses: list[str] = None
    technique_comparison: dict[str, dict] = None  # 技巧使用对比

    def __post_init__(self):
        if self.strengths is None:
            self.strengths = []
        if self.weaknesses is None:
            self.weaknesses = []
        if self.technique_comparison is None:
            self.technique_comparison = {}


# ═══════════════════════════════════════════════════════════════
# ContextBuilder
# ═══════════════════════════════════════════════════════════════


class ContextBuilder:
    """从 MindEcho 的 PitchFrame / 分析 JSON 构建 LLM 上下文"""

    def __init__(self):
        self._last_context: Optional[SingingContext] = None

    # ── 输入解析 ─────────────────────────────────────────────

    def from_analysis_json(self, json_path: str | Path) -> SingingContext:
        """从 MindEcho 生成的 _analysis.json 文件构建上下文"""
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return self.from_dict(data)

    def from_dict(self, data: dict) -> SingingContext:
        """从 MindEcho 分析 dict 构建上下文"""
        # 兼容两种 JSON 结构：pitch_data 在顶层或在 pitch_analysis 子对象内
        if "pitch_data" not in data and "pitch_analysis" in data:
            pa = data.get("pitch_analysis", {})
            if isinstance(pa, dict) and "pitch_data" in pa:
                data["pitch_data"] = pa["pitch_data"]
        # 归一化时间戳：将绝对 Unix 时间戳转为从 0 开始的相对秒数
        self._normalize_timestamps(data)
        ctx = SingingContext()
        ctx.stats = self._build_pitch_stats(data)
        ctx.segments = self._build_segments(data)
        ctx.techniques = self._build_technique_summary(data)
        ctx.breath_analysis = self._build_breath_analysis(data)
        ctx.segment_stability = self._build_segment_stability(data)
        ctx.pitch_drift = self._build_pitch_drift(data)
        self._last_context = ctx
        return ctx

    @staticmethod
    def _normalize_timestamps(data: dict):
        """将 pitch_data 和 technique_events 中的绝对时间戳归一化为从 0 开始。"""
        pitch_data = data.get("pitch_data", [])
        if not pitch_data:
            return

        # 查找最小 timestamp
        timestamps = []
        for p in pitch_data:
            t = p.get("timestamp")
            if t is not None and t > 1000000000:  # Unix 时间戳特征 (>2001年)
                timestamps.append(t)
        if not timestamps:
            return

        t0 = min(timestamps)
        if t0 < 1000000000:  # 已经是相对时间，不用转换
            return

        for p in pitch_data:
            t = p.get("timestamp")
            if t is not None:
                p["timestamp"] = t - t0

        for ev in data.get("technique_events", []):
            for key in ("start_time", "end_time", "center_time"):
                t = ev.get(key)
                if t is not None and t > 1000000000:
                    ev[key] = t - t0

    def from_pitch_frames(
        self,
        frames: list[dict],       # PitchFrame.to_dict() 列表
        technique_events: Optional[list[dict]] = None,
    ) -> SingingContext:
        """直接从 PitchFrame 列表构建上下文"""
        data = {
            "pitch_data": frames,
            "technique_events": technique_events or [],
        }
        return self.from_dict(data)

    # ── L1 统计摘要 ───────────────────────────────────────────

    # 低于此置信度的帧视为噪声/无效检测，不计入有声统计
    _MIN_VOICED_CONFIDENCE = 0.40
    # 有效人声占比低于此值 → 判定为"未检测到有效人声"
    _MIN_VOICED_RATIO = 0.10

    def _build_pitch_stats(self, data: dict) -> PitchStats:
        pitch_data = data.get("pitch_data", [])
        if not pitch_data:
            return PitchStats(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

        frames = []
        for p in pitch_data:
            f0 = (p.get("f0_smooth") or p.get("detected_frequency")
                  or p.get("f0_raw") or p.get("frequency") or 0)
            conf = p.get("confidence", 0)
            has_pitch = p.get("has_pitch", f0 > 60)
            frames.append({"f0": f0, "conf": conf, "has_pitch": has_pitch})

        voiced = [f for f in frames
                   if f["has_pitch"] and f["f0"] > 60
                   and f["conf"] >= self._MIN_VOICED_CONFIDENCE]
        if not voiced:
            return PitchStats(len(frames), 0, 0, 0, 0, 0, 0, 0, 0, 0)

        freqs = np.array([f["f0"] for f in voiced])
        confs = np.array([f["conf"] for f in voiced])

        # 如果有参考音符信息，计算音分偏差（保留符号用于偏高/偏低统计）
        cent_devs = []
        for p in pitch_data:
            conf = p.get("confidence", 0)
            if conf < self._MIN_VOICED_CONFIDENCE:
                continue
            note_info = p.get("note_info", {}) or {}
            cd = note_info.get("cents_deviation") or note_info.get("cent_deviation") or note_info.get("cents")
            if cd is not None:
                cent_devs.append(float(cd))

        if cent_devs:
            cent_arr = np.array([abs(cd) for cd in cent_devs])
            mean_dev = float(np.mean(cent_arr))
            std_dev = float(np.std(cent_arr))
            # 25 音分约等于四分之一半音，是人耳能分辨的合理阈值
            accuracy = float(np.mean(cent_arr < 25))
            raw_arr = np.array(cent_devs)
            sharp_ratio = float(np.mean(raw_arr > 10))
            flat_ratio = float(np.mean(raw_arr < -10))
        else:
            mean_dev = 0.0
            std_dev = 0.0
            accuracy = float(np.mean(confs > 0.6)) if len(confs) > 0 else 0.0
            sharp_ratio = 0.5
            flat_ratio = 0.5

        return PitchStats(
            total_frames=len(frames),
            voiced_frames=len(voiced),
            pitch_accuracy=round(accuracy, 3),
            mean_cent_deviation=round(mean_dev, 1),
            std_cent_deviation=round(std_dev, 1),
            sharp_ratio=round(sharp_ratio, 3),
            flat_ratio=round(flat_ratio, 3),
            min_freq=round(float(np.min(freqs)), 1),
            max_freq=round(float(np.max(freqs)), 1),
            mean_confidence=round(float(np.mean(confs)), 3),
        )

    # ── L2 分段描述 ───────────────────────────────────────────

    def _build_segments(self, data: dict) -> list[SegmentAnalysis]:
        """将音高数据自动分段并标注问题区域"""
        pitch_data = data.get("pitch_data", [])
        if len(pitch_data) < 100:
            return []

        segments = []
        chunk_size = max(200, len(pitch_data) // 4)

        for i in range(0, len(pitch_data), chunk_size):
            chunk = pitch_data[i:i + chunk_size]
            start_t = chunk[0].get("timestamp", i / 64.0)
            end_t = chunk[-1].get("timestamp", (i + len(chunk)) / 64.0)

            cent_devs = []
            for p in chunk:
                conf = p.get("confidence", 0)
                if conf < self._MIN_VOICED_CONFIDENCE:
                    continue
                ni = p.get("note_info", {}) or {}
                cd = ni.get("cents_deviation") or ni.get("cent_deviation") or ni.get("cents")
                if cd is not None:
                    cent_devs.append(abs(cd))

            accuracy = 1.0 - (np.mean(cent_devs) / 100) if cent_devs else 0.5
            accuracy = max(0.0, min(1.0, accuracy))

            issues = []
            if cent_devs and np.mean(cent_devs) > 40:
                issues.append("音准偏差较大")
            confs = [p.get("confidence", 0) for p in chunk if p.get("has_pitch", True)]
            if confs and np.mean(confs) < 0.5:
                issues.append("音高检测置信度偏低")
            if len(chunk) < chunk_size // 2:
                issues.append("本段数据不足")

            segment_num = i // chunk_size + 1
            label = f"段落 {segment_num}"
            segments.append(SegmentAnalysis(start_t, end_t, label, round(accuracy, 3), issues))

        return segments

    # ── 技巧摘要 ──────────────────────────────────────────────

    def _build_technique_summary(self, data: dict) -> TechniqueSummary:
        events = data.get("technique_events", [])
        if not events:
            return TechniqueSummary()

        ts = TechniqueSummary()
        voice_types = {"chest": 0, "falsetto": 0, "mix": 0, "head": 0}

        for ev in events:
            etype = ev.get("event_type") or ev.get("type", "")
            if etype == "vibrato":
                ts.vibrato_count += 1
                ts.vibrato_avg_rate += ev.get("rate_hz", 0)
                ts.vibrato_avg_depth += ev.get("depth_cents", 0)
            elif etype == "slide":
                ts.slide_count += 1
            elif etype == "breath":
                ts.breath_count += 1
            elif etype == "register_transition":
                ts.register_transition_count += 1
            elif etype == "breathy_phonation":
                ts.breathiness_score = max(ts.breathiness_score, ev.get("score", 0))
            elif etype in ("voice_type", "chest", "falsetto", "mix"):
                vt = ev.get("voice_type", etype)
                voice_types[vt] = voice_types.get(vt, 0) + 1

        if ts.vibrato_count > 0:
            ts.vibrato_avg_rate /= ts.vibrato_count
            ts.vibrato_avg_depth /= ts.vibrato_count

        total_vt = sum(voice_types.values())
        if total_vt > 0:
            ts.voice_type_distribution = {k: round(v / total_vt, 3) for k, v in voice_types.items()}

        return ts

    # ── L2 增强：换气分析 ──────────────────────────────────────

    def _build_breath_analysis(self, data: dict) -> str:
        """从 technique_events 中提取呼吸事件的详细分析。

        每个 BreathEvent 有 10+ 子字段，这里输出表格 + 自动问题标注。
        """
        events = data.get("technique_events", [])
        breaths = [e for e in events if e.get("event_type") == "breath" or e.get("type") == "breath"]
        if not breaths:
            return ""

        lines = ["【换气分析】"]

        # 表头
        lines.append(
            "| 时间 | 类型 | 深度(RMS) | 杂音(ZCR) | 换气前音高 | 换气后音高 | 恢复时间 |"
        )
        lines.append(
            "|------|------|-----------|-----------|-----------|-----------|---------|"
        )

        problems = []
        for b in breaths:
            t = float(b.get("start_time", 0))
            subtype = str(b.get("subtype", "normal"))
            rms = float(b.get("mean_rms", 0) or 0)
            zcr = float(b.get("mean_zcr", 0) or 0)
            pre = float(b.get("pre_pitch_hz", 0) or 0)
            post = float(b.get("post_pitch_hz", 0) or 0)
            recovery = float(b.get("recovery_delay_ms", 0) or 0)

            pre_str = f"{self._hz_to_note(pre)}" if pre > 60 else "-"
            post_str = f"{self._hz_to_note(post)}" if post > 60 else "-"

            # 标注换气后音高变化
            delta_str = ""
            if pre > 60 and post > 60:
                delta_semi = abs(12.0 * np.log2(max(pre, post) / max(min(pre, post), 1.0)))
                if delta_semi > 0.5:
                    direction = "↓" if post < pre else "↑"
                    post_str += f"{direction}"

            rec_str = f"{recovery:.0f}ms" if recovery > 0 else "-"

            lines.append(
                f"| {t:.1f}s | {subtype} | {rms:.4f} | {zcr:.2f} | "
                f"{pre_str} | {post_str} | {rec_str} |"
            )

            # 自动问题检测
            if pre > 60 and post > 60:
                delta_semi_abs = abs(12.0 * np.log2(max(pre, post) / max(min(pre, post), 1.0)))
                if delta_semi_abs > 0.5:
                    direction_text = "偏低" if post < pre else "偏高"
                    problems.append(
                        f"{t:.1f}s: 换气后音高{direction_text}{delta_semi_abs:.1f}半音"
                        f"({self._hz_to_note(pre)}→{self._hz_to_note(post)})，气息支撑可能断开"
                    )
            if rms > 0 and rms < 0.002:
                problems.append(f"{t:.1f}s: 换气深度过浅(RMS={rms:.4f})，可能没吸够气")
            if zcr > 0.25:
                problems.append(f"{t:.1f}s: 换气杂音偏高(ZCR={zcr:.2f})，换气声较大")
            if recovery > 150:
                problems.append(f"{t:.1f}s: 换气后恢复偏慢({recovery:.0f}ms)，建议缩短换气间隙")

        if problems:
            lines.append("")
            lines.append("⚠ 问题换气:")
            for p in problems:
                lines.append(f"  - {p}")

        return "\n".join(lines)

    @staticmethod
    def _hz_to_note(hz: float) -> str:
        if hz <= 0:
            return "-"
        notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        semitones = 12.0 * np.log2(hz / 440.0)
        note_idx = (9 + round(semitones)) % 12
        octave = 4 + (9 + round(semitones)) // 12
        return f"{notes[note_idx]}{octave}"

    # ── L2 增强：逐段稳定性 ────────────────────────────────────

    def _build_segment_stability(self, data: dict) -> str:
        """按段落计算局部稳定性（std_cent_deviation），替代全局单一数字。

        复用 _build_segments 的分段逻辑，在每个段落内额外计算 cent 标准差。
        """
        pitch_data = data.get("pitch_data", [])
        if len(pitch_data) < 100:
            return ""

        # 收集每个帧的时间戳和 cent deviation（仅高置信度帧）
        frames = []
        for p in pitch_data:
            conf = p.get("confidence", 0)
            if conf < self._MIN_VOICED_CONFIDENCE:
                continue
            t = p.get("timestamp", 0)
            ni = p.get("note_info", {}) or {}
            cd = ni.get("cents_deviation") or ni.get("cent_deviation") or ni.get("cents")
            if cd is not None and t is not None:
                frames.append((float(t), float(cd)))

        if not frames:
            return ""

        chunk_size = max(200, len(frames) // 4)
        seg_results = []

        for i in range(0, len(frames), chunk_size):
            chunk = frames[i:i + chunk_size]
            if len(chunk) < 30:
                continue
            start_t = chunk[0][0]
            end_t = chunk[-1][0]
            devs = [abs(c[1]) for c in chunk]
            mean_dev = float(np.mean(devs))
            std_dev = float(np.std(devs))
            max_dev = float(np.max(devs))
            segment_num = i // chunk_size + 1

            # 判断稳定性等级
            if std_dev < 25:
                status = "✓ 稳定"
            elif std_dev < 45:
                status = "△ 一般"
            else:
                status = "⚠ 不稳定"

            # 找出波动最大的区域（前 3 个最大偏差）
            top_indices = np.argsort(devs)[-3:]
            top_info = []
            for idx in top_indices:
                if devs[idx] > 30:
                    t = chunk[idx][0]
                    top_info.append(f"{t:.1f}s(+{abs(chunk[idx][1]):.0f}音分)")

            detail = ""
            if top_info:
                detail = f"，最大偏差: {', '.join(top_info)}"

            seg_results.append(
                f"段落{segment_num} ({start_t:.0f}-{end_t:.0f}s): "
                f"稳定性 {std_dev:.0f}音分 {status}"
                f"{detail}"
            )

        if not seg_results:
            return ""

        return "【逐段稳定性】\n" + "\n".join(seg_results)

    # ── L2 增强：音高漂移趋势 ──────────────────────────────────

    def _build_pitch_drift(self, data: dict) -> str:
        """用线性回归检测音高随时间的系统性偏移（很多人越唱越偏低）。"""
        pitch_data = data.get("pitch_data", [])
        if len(pitch_data) < 200:
            return ""

        # 收集 (时间, cent_deviation)（仅高置信度帧）
        points = []
        for p in pitch_data:
            conf = p.get("confidence", 0)
            if conf < self._MIN_VOICED_CONFIDENCE:
                continue
            t = p.get("timestamp", 0)
            ni = p.get("note_info", {}) or {}
            cd = ni.get("cents_deviation") or ni.get("cent_deviation") or ni.get("cents")
            if cd is not None and t is not None:
                points.append((float(t), float(cd)))

        if len(points) < 100:
            return ""

        times = np.array([p[0] for p in points])
        devs = np.array([p[1] for p in points])

        # 简单线性回归: dev = slope * time + intercept
        n = len(times)
        mean_t = np.mean(times)
        mean_d = np.mean(devs)
        slope = np.sum((times - mean_t) * (devs - mean_d)) / max(np.sum((times - mean_t) ** 2), 1e-9)
        intercept = mean_d - slope * mean_t

        # 前半 vs 后半对比
        mid_t = (times[0] + times[-1]) / 2
        first_half = devs[times < mid_t]
        second_half = devs[times >= mid_t]
        first_mean = float(np.mean(first_half)) if len(first_half) > 0 else 0.0
        second_mean = float(np.mean(second_half)) if len(second_half) > 0 else 0.0
        drift = second_mean - first_mean

        total_sec = times[-1] - times[0]
        drift_per_min = (slope * 60.0)

        lines = ["【音高漂移分析】"]

        if abs(drift) < 8:
            lines.append("整体趋势: 无明显漂移，音高保持稳定 ✓")
        else:
            direction = "偏低" if drift < 0 else "偏高"
            severity = "⚠ 显著" if abs(drift) > 20 else "△ 轻微"
            lines.append(
                f"整体趋势: 后半段比前半段平均{direction} {abs(drift):.0f} 音分 ({severity})"
            )
            drift_dir = "走低" if slope < 0 else "走高"
            lines.append(f"漂移速率: 每分钟{drift_dir}约 {abs(drift_per_min):.0f} 音分")

            # 找最严重漂移的时间段
            if abs(drift) > 15:
                window = max(50, n // 8)
                max_drift = 0.0
                max_drift_start = 0.0
                for i in range(0, n - window, window // 2):
                    w_devs = devs[i:i + window]
                    w_drift = float(np.mean(w_devs[-window//4:]) - np.mean(w_devs[:window//4]))
                    if abs(w_drift) > abs(max_drift):
                        max_drift = w_drift
                        max_drift_start = times[i]
                if abs(max_drift) > abs(drift) * 0.8:
                    lines.append(
                        f"最严重漂移: {max_drift_start:.0f}s 附近"
                        f"({max_drift:+.0f}音分)"
                    )

            if abs(drift) > 20:
                lines.append("建议: 注意呼吸支撑的持续性，越往后越要有意识保持气息压力")

        return "\n".join(lines)

    # ── LLM 文本生成 (金字塔压缩) ─────────────────────────────

    def build_l1_summary(self, ctx: Optional[SingingContext] = None) -> str:
        """L1 摘要 (~200 tokens) —— 整体音准和关键指标"""
        ctx = ctx or self._last_context
        if ctx is None or ctx.stats is None:
            return "（暂无演唱数据）"

        s = ctx.stats
        lines = [
            "【本次演唱 L1 统计摘要】",
            f"有声帧: {s.voiced_frames}/{s.total_frames}",
            f"音准命中率: {s.pitch_accuracy:.0%}（±50音分内）",
            f"平均音分偏差: {s.mean_cent_deviation:.0f} 音分",
            f"音高分差: {s.std_cent_deviation:.0f} 音分（稳定性）",
            f"偏高比例: {s.sharp_ratio:.0%} | 偏低比例: {s.flat_ratio:.0%}",
            f"音域: {s.min_freq:.0f}Hz - {s.max_freq:.0f}Hz",
            f"平均置信度: {s.mean_confidence:.0%}",
        ]
        return "\n".join(lines)

    def build_l2_description(self, ctx: Optional[SingingContext] = None) -> str:
        """L2 分段描述 (~500 tokens) —— 段落级分析和问题标注"""
        ctx = ctx or self._last_context
        if ctx is None or not ctx.segments:
            return ""

        lines = ["【分段分析】"]
        for seg in ctx.segments:
            status = "✓" if seg.accuracy > 0.8 else "△" if seg.accuracy > 0.6 else "✗"
            lines.append(
                f"{status} {seg.label} ({seg.start_time:.1f}s-{seg.end_time:.1f}s): "
                f"准确度 {seg.accuracy:.0%}"
            )
            if seg.issues:
                for issue in seg.issues:
                    lines.append(f"   ⚠ {issue}")
        return "\n".join(lines)

    def build_technique_report(self, ctx: Optional[SingingContext] = None) -> str:
        """技巧使用报告"""
        ctx = ctx or self._last_context
        if ctx is None or ctx.techniques is None:
            return ""

        t = ctx.techniques
        lines = ["【技巧检测摘要】"]

        if t.vibrato_count > 0:
            lines.append(
                f"颤音: {t.vibrato_count} 次, "
                f"平均速率 {t.vibrato_avg_rate:.1f}Hz, "
                f"平均深度 {t.vibrato_avg_depth:.0f} 音分"
            )
        else:
            lines.append("颤音: 未检测到")

        lines.append(f"滑音事件: {t.slide_count}")
        lines.append(f"换气事件: {t.breath_count}")
        lines.append(f"声区切换: {t.register_transition_count}")

        if t.voice_type_distribution:
            vtd = t.voice_type_distribution
            parts = [f"{k}: {v:.0%}" for k, v in vtd.items()]
            lines.append(f"声音类型分布: {', '.join(parts)}")

        return "\n".join(lines)

    def build_comparison_report(self, ctx: Optional[SingingContext] = None) -> str:
        """对比分析报告"""
        ctx = ctx or self._last_context
        if ctx is None or ctx.comparison is None:
            return ""

        c = ctx.comparison
        lines = [
            "【专业歌手对比分析】",
            f"参考歌手: {c.reference_name}",
            f"综合音准差距: {c.overall_accuracy_gap:.0f} 音分",
        ]
        if c.best_segment:
            lines.append(f"最佳段落: {c.best_segment}")
        if c.worst_segment:
            lines.append(f"最需改进段落: {c.worst_segment}")
        if c.strengths:
            lines.append(f"优势: {', '.join(c.strengths)}")
        if c.weaknesses:
            lines.append(f"需改进: {', '.join(c.weaknesses)}")
        if c.technique_comparison:
            lines.append("技巧使用对比:")
            for tech, comp in c.technique_comparison.items():
                lines.append(f"  {tech}: 你 {comp.get('user', 'N/A')} vs 参考 {comp.get('ref', 'N/A')}")
        return "\n".join(lines)

    def build_full_context(
        self,
        ctx: Optional[SingingContext] = None,
        level: str = "l1",
    ) -> str:
        """根据需求级别构建完整上下文

        Args:
            ctx: 演唱上下文
            level: "l1" (基础摘要), "l2" (分段分析), "l3" (含对比)
        """
        ctx = ctx or self._last_context
        if ctx is None:
            return "（暂无演唱数据，请先进行录音分析）"

        if not ctx.has_valid_singing:
            parts = [self.build_l1_summary(ctx)]
            parts.append(
                "⚠ 未检测到有效人声。可能原因：\n"
                "- 录音时麦克风未开启或权限被拒绝\n"
                "- 录音环境中背景噪音过大\n"
                "- 人声信号过弱（离麦克风太远或音量太低）\n"
                "请检查麦克风设置后重新录制。"
            )
            return "\n\n".join(parts)

        parts = [self.build_l1_summary(ctx)]

        if level in ("l2", "l3"):
            desc = self.build_l2_description(ctx)
            if desc:
                parts.append(desc)
            tech = self.build_technique_report(ctx)
            if tech:
                parts.append(tech)
            # v2 增强特征
            if ctx.breath_analysis:
                parts.append(ctx.breath_analysis)
            if ctx.segment_stability:
                parts.append(ctx.segment_stability)
            if ctx.pitch_drift:
                parts.append(ctx.pitch_drift)

        if level == "l3":
            comp = self.build_comparison_report(ctx)
            if comp:
                parts.append(comp)

        return "\n\n".join(parts)
