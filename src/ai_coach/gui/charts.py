"""轻量级 SVG 图表生成器 —— 用于练习数据可视化，零外部依赖"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Optional


def sparkline_svg(
    values: list[float],
    width: int = 300,
    height: int = 60,
    line_color: str = "#7C5CFC",
    fill_color: str = "rgba(124, 92, 252, 0.15)",
    labels: Optional[list[str]] = None,
) -> str:
    """生成迷你折线图 SVG。

    Args:
        values: 0.0-1.0 的数值列表
        width/height: 图表尺寸
        line_color: 线条颜色
        fill_color: 填充颜色
        labels: X 轴标签（可选）
    """
    if not values or len(values) < 2:
        return '<div style="color:#666;font-size:11px;padding:10px;">暂无足够数据绘制图表</div>'

    n = len(values)
    pad_left, pad_right = 10, 10
    pad_top, pad_bottom = 10, 16
    chart_w = width - pad_left - pad_right
    chart_h = height - pad_top - pad_bottom

    # 坐标映射
    min_val = min(values) * 0.9
    max_val = max(values) * 1.1
    val_range = max_val - min_val or 0.01

    def x(i: int) -> float:
        return pad_left + (i / (n - 1)) * chart_w

    def y(v: float) -> float:
        return pad_top + chart_h - ((v - min_val) / val_range) * chart_h

    # 构建路径
    points = [(x(i), y(v)) for i, v in enumerate(values)]

    path_d = "M " + " L ".join(f"{px:.1f},{py:.1f}" for px, py in points)
    fill_d = (
        f"M {points[0][0]:.1f},{height - pad_bottom} "
        + f"L {points[0][0]:.1f},{points[0][1]:.1f} "
        + " L ".join(f"{px:.1f},{py:.1f}" for px, py in points[1:])
        + f" L {points[-1][0]:.1f},{height - pad_bottom} Z"
    )

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<path d="{fill_d}" fill="{fill_color}" stroke="none"/>',
        f'<path d="{path_d}" fill="none" stroke="{line_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
    ]

    # 数据点
    for px, py in points:
        parts.append(
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="2.5" fill="{line_color}" stroke="#1a1a2e" stroke-width="1"/>'
        )

    # X 轴标签
    if labels:
        step = max(1, (n - 1) // 5)
        for i in range(0, n, step):
            lbl = labels[i]
            parts.append(
                f'<text x="{x(i):.1f}" y="{height - 3}" '
                f'text-anchor="middle" font-size="9" fill="#888">{lbl}</text>'
            )

    parts.append("</svg>")
    return "\n".join(parts)


def bar_chart_svg(
    data: list[tuple[str, float]],
    width: int = 320,
    height: int = 140,
    bar_color: str = "#7C5CFC",
    bar_color_alt: str = "#A78BFA",
    max_label: str = "100%",
) -> str:
    """生成柱状图 SVG。

    Args:
        data: (标签, 值) 列表，值应为 0.0-1.0
    """
    if not data:
        return '<div style="color:#666;font-size:11px;padding:10px;">暂无数据</div>'

    n = len(data)
    pad_left, pad_right = 36, 10
    pad_top, pad_bottom = 8, 24
    chart_w = width - pad_left - pad_right
    chart_h = height - pad_top - pad_bottom
    bar_gap = 6
    bar_w = max(4, (chart_w - bar_gap * (n + 1)) / n)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        # Y 轴参考线
        f'<line x1="{pad_left}" y1="{pad_top}" x2="{pad_left}" y2="{pad_top + chart_h}" stroke="#444" stroke-width="1"/>',
        f'<line x1="{pad_left}" y1="{pad_top + chart_h}" x2="{width - pad_right}" y2="{pad_top + chart_h}" stroke="#444" stroke-width="1"/>',
    ]

    # 50% 参考线
    mid_y = pad_top + chart_h / 2
    parts.append(
        f'<line x1="{pad_left}" y1="{mid_y:.1f}" x2="{width - pad_right}" y2="{mid_y:.1f}" '
        f'stroke="#333" stroke-width="1" stroke-dasharray="4,4"/>'
    )
    parts.append(
        f'<text x="{pad_left - 6}" y="{mid_y + 4:.1f}" text-anchor="end" font-size="9" fill="#666">50%</text>'
    )
    parts.append(
        f'<text x="{pad_left - 6}" y="{pad_top + 5:.1f}" text-anchor="end" font-size="9" fill="#666">{max_label}</text>'
    )

    for i, (label, val) in enumerate(data):
        bar_h = max(2, val * chart_h)
        bx = pad_left + bar_gap + i * (bar_w + bar_gap)
        by = pad_top + chart_h - bar_h
        color = bar_color if i % 2 == 0 else bar_color_alt

        # 圆角矩形（简化：用 rx/ry）
        parts.append(
            f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" '
            f'rx="3" ry="3" fill="{color}" opacity="0.85"/>'
        )

        # 数值标签
        pct = f"{val * 100:.0f}%"
        parts.append(
            f'<text x="{bx + bar_w / 2:.1f}" y="{by - 4:.1f}" '
            f'text-anchor="middle" font-size="8" fill="#ccc">{pct}</text>'
        )

        # X 轴标签
        parts.append(
            f'<text x="{bx + bar_w / 2:.1f}" y="{height - 6}" '
            f'text-anchor="middle" font-size="9" fill="#999">{label}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def progress_ring_svg(
    value: float,
    size: int = 80,
    stroke_width: int = 6,
    color: str = "#4ADE80",
    bg_color: str = "#333",
    label: str = "",
) -> str:
    """生成进度圆环 SVG。

    Args:
        value: 0.0-1.0
        size: 直径
        label: 居中文字
    """
    r = (size - stroke_width) / 2
    cx, cy = size / 2, size / 2
    circumference = 2 * math.pi * r
    dash_offset = circumference * (1 - value)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">',
        # 背景圆环
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="none" '
        f'stroke="{bg_color}" stroke-width="{stroke_width}"/>',
        # 进度圆环
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="none" '
        f'stroke="{color}" stroke-width="{stroke_width}" '
        f'stroke-dasharray="{circumference:.1f}" stroke-dashoffset="{dash_offset:.1f}" '
        f'stroke-linecap="round" transform="rotate(-90 {cx:.1f} {cy:.1f})"/>',
    ]

    if label:
        parts.append(
            f'<text x="{cx:.1f}" y="{cy + 4:.1f}" text-anchor="middle" '
            f'font-size="14" font-weight="bold" fill="#e0e0e0">{label}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)
