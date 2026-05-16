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
        ctx = SingingContext()
        ctx.stats = self._build_pitch_stats(data)
        ctx.segments = self._build_segments(data)
        ctx.techniques = self._build_technique_summary(data)
        self._last_context = ctx
        return ctx

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

    def _build_pitch_stats(self, data: dict) -> PitchStats:
        pitch_data = data.get("pitch_data", [])
        if not pitch_data:
            return PitchStats(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

        frames = []
        for p in pitch_data:
            f0 = p.get("f0_smooth") or p.get("detected_frequency") or p.get("f0_raw") or 0
            conf = p.get("confidence", 0)
            has_pitch = p.get("has_pitch", f0 > 60)
            frames.append({"f0": f0, "conf": conf, "has_pitch": has_pitch})

        voiced = [f for f in frames if f["has_pitch"] and f["f0"] > 60]
        if not voiced:
            return PitchStats(len(frames), 0, 0, 0, 0, 0, 0, 0, 0, 0)

        freqs = np.array([f["f0"] for f in voiced])
        confs = np.array([f["conf"] for f in voiced])

        # 如果有参考音符信息，计算音分偏差
        cent_devs = []
        for p in pitch_data:
            note_info = p.get("note_info", {})
            if note_info and note_info.get("cents_deviation") is not None:
                cent_devs.append(abs(note_info["cents_deviation"]))
            elif note_info and note_info.get("cent_deviation") is not None:
                cent_devs.append(abs(note_info["cent_deviation"]))

        if cent_devs:
            cent_arr = np.array(cent_devs)
            mean_dev = float(np.mean(cent_arr))
            std_dev = float(np.std(cent_arr))
            accuracy = float(np.mean(cent_arr < 50))  # 50 音分内算准确
            sharp_ratio = float(np.mean(np.array(cent_devs) > 0)) if cent_devs else 0.5
            flat_ratio = 1.0 - sharp_ratio
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
                ni = p.get("note_info", {})
                cd = ni.get("cents_deviation") or ni.get("cent_deviation")
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
            etype = ev.get("type", "")
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

        parts = [self.build_l1_summary(ctx)]

        if level in ("l2", "l3"):
            desc = self.build_l2_description(ctx)
            if desc:
                parts.append(desc)
            tech = self.build_technique_report(ctx)
            if tech:
                parts.append(tech)

        if level == "l3":
            comp = self.build_comparison_report(ctx)
            if comp:
                parts.append(comp)

        return "\n\n".join(parts)
