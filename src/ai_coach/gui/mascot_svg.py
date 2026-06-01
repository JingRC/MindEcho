"""MindEcho AI 声乐教练桌宠 —— 多角色 SVG 形象系统 V5

设计参考: Pokemon(皮卡丘/伊布/百变怪) + Sanrio + LINE Friends 萌系比例
核心原则:
  1. 扁平色块 + 极简渐变，拒绝复杂阴影
  2. 腮红 > 眼睛 (皮卡丘式大腮红)
  3. 所有形状来自圆圈和圆角，无尖角
  4. 头身比 ~1:1，头部占 50-55% 总高
  5. 头身重叠 ~20-30px，无缝堆叠
  6. 粗描边，贴纸感

角色:
  麦麦   — 音乐小猫 (皮卡丘比例)
  团团   — 豆豆小熊 (松弛熊风格)
  音音   — 破壳小鸡 (单一体+蛋壳底座, 无头身分离)
  球球   — 水滴史莱姆 (百变怪极简风)
  绵绵   — 垂耳兔兔 (伊布长耳风格)
"""

# ═══════════════════════════════════════════════════════════════
# 角色元数据
# ═══════════════════════════════════════════════════════════════

CHARACTERS = {
    "maimai":   {"name": "麦麦", "desc": "音乐小猫"},
    "tuantuan": {"name": "团团", "desc": "豆豆小熊"},
    "yinyin":   {"name": "音音", "desc": "破壳小鸡"},
    "qiuqiu":   {"name": "球球", "desc": "水滴史莱姆"},
    "mianmian": {"name": "绵绵", "desc": "垂耳兔兔"},
}

# ═══════════════════════════════════════════════════════════════
# 11 套主题 (扁色调色盘，每角色2-4色)
# ═══════════════════════════════════════════════════════════════

THEMES = {
    # ── 麦麦 (MaiMai) ──
    "classic": {
        "name": "麦麦·经典紫", "character": "maimai",
        "body": "#B794F4", "body_light": "#DDD6FE", "body_dark": "#7C3AED",
        "belly": "#F5F3FF", "cheek": "#FF8DA6",
        "ear_inner": "#F6C8DC", "accent": "#FF6B9D",
        "headphone": "#4C1D95", "headphone_pad": "#F9A8D4",
        "mic": "#FFD93D", "mic_body": "#4C1D95",
        "scarf": "#FF6B9D", "note": "#6EE7B7", "star": "#FFD93D",
    },
    "ocean": {
        "name": "麦麦·海洋蓝", "character": "maimai",
        "body": "#74B9F6", "body_light": "#BFDBFE", "body_dark": "#2563EB",
        "belly": "#EFF6FF", "cheek": "#FF8DA6",
        "ear_inner": "#FDE2F0", "accent": "#38BDF8",
        "headphone": "#1E3A5F", "headphone_pad": "#93D9FC",
        "mic": "#FBBF24", "mic_body": "#1E3A5F",
        "scarf": "#38BDF8", "note": "#34D399", "star": "#FBBF24",
    },
    "midnight": {
        "name": "麦麦·暗夜紫", "character": "maimai",
        "body": "#C4A5F6", "body_light": "#E9D5FF", "body_dark": "#8B5CF6",
        "belly": "#FAF5FF", "cheek": "#FDA4D6",
        "ear_inner": "#EDE4F6", "accent": "#D8B4FE",
        "headphone": "#581C87", "headphone_pad": "#E2C6FB",
        "mic": "#F472B6", "mic_body": "#581C87",
        "scarf": "#E2C6FB", "note": "#22D3EE", "star": "#F472B6",
    },
    # ── 团团 (TuanTuan) ──
    "honey": {
        "name": "团团·蜂蜜棕", "character": "tuantuan",
        "body": "#F0A854", "body_light": "#FDE68A", "body_dark": "#D97706",
        "belly": "#FFFBEB", "cheek": "#FDBA74",
        "ear_inner": "#FEF3C7", "accent": "#EF4444",
        "headphone": "#78350F", "headphone_pad": "#FDE68A",
        "mic": "#FBBF24", "mic_body": "#78350F",
        "scarf": "#EF4444", "note": "#34D399", "star": "#FBBF24",
    },
    "caramel": {
        "name": "团团·焦糖橘", "character": "tuantuan",
        "body": "#F8905C", "body_light": "#FED7AA", "body_dark": "#EA580C",
        "belly": "#FFF7ED", "cheek": "#FDBA74",
        "ear_inner": "#FFEDD5", "accent": "#F472B6",
        "headphone": "#7C2D12", "headphone_pad": "#FED7AA",
        "mic": "#FDE047", "mic_body": "#7C2D12",
        "scarf": "#F472B6", "note": "#A78BFA", "star": "#FDE047",
    },
    # ── 音音 (YinYin) ──
    "mint": {
        "name": "音音·薄荷绿", "character": "yinyin",
        "body": "#5EDB82", "body_light": "#BBF7D0", "body_dark": "#16A34A",
        "belly": "#F0FDF4", "cheek": "#FF8DA6",
        "ear_inner": "#DCFCE7", "accent": "#FBBF24",
        "headphone": "#14532D", "headphone_pad": "#86EFAC",
        "mic": "#FBBF24", "mic_body": "#14532D",
        "scarf": "#86EFAC", "note": "#A78BFA", "star": "#FBBF24",
    },
    "sky": {
        "name": "音音·天蓝", "character": "yinyin",
        "body": "#6DBEF4", "body_light": "#BAE6FD", "body_dark": "#2563EB",
        "belly": "#F0F9FF", "cheek": "#FF8DA6",
        "ear_inner": "#E0F2FE", "accent": "#FBBF24",
        "headphone": "#1E40AF", "headphone_pad": "#93D9FC",
        "mic": "#FDE047", "mic_body": "#1E40AF",
        "scarf": "#BAE6FD", "note": "#F472B6", "star": "#FDE047",
    },
    # ── 球球 (QiuQiu) ──
    "sunset": {
        "name": "球球·暖橙", "character": "qiuqiu",
        "body": "#FF9A6C", "body_light": "#FFD4BE", "body_dark": "#E8652C",
        "belly": "#FFF5F0", "cheek": "#FFB0C0",
        "ear_inner": "#FFE8DC", "accent": "#FDE047",
        "headphone": "#7C2D12", "headphone_pad": "#FCD34D",
        "mic": "#FDE047", "mic_body": "#7C2D12",
        "scarf": "#FCD34D", "note": "#4ADE80", "star": "#FDE047",
    },
    "bubblegum": {
        "name": "球球·泡泡糖", "character": "qiuqiu",
        "body": "#F4A3C8", "body_light": "#FCE7F3", "body_dark": "#DB3980",
        "belly": "#FDF2F8", "cheek": "#FDCFBC",
        "ear_inner": "#FCE7F3", "accent": "#FDE047",
        "headphone": "#831843", "headphone_pad": "#FBCFE8",
        "mic": "#FDE047", "mic_body": "#831843",
        "scarf": "#FDE047", "note": "#34D399", "star": "#FDE047",
    },
    # ── 绵绵 (MianMian) ──
    "sakura": {
        "name": "绵绵·樱花粉", "character": "mianmian",
        "body": "#FFCCDA", "body_light": "#FFE4EC", "body_dark": "#F9A8C9",
        "belly": "#FFF5F8", "cheek": "#FFB0C0",
        "ear_inner": "#FFE4EC", "accent": "#C084FC",
        "headphone": "#9D174D", "headphone_pad": "#F9A8D4",
        "mic": "#FDE047", "mic_body": "#9D174D",
        "scarf": "#E879F9", "note": "#6EE7B7", "star": "#FDE047",
    },
    "snow": {
        "name": "绵绵·雪白", "character": "mianmian",
        "body": "#F0F3F6", "body_light": "#FFFFFF", "body_dark": "#CBD5E1",
        "belly": "#FFFFFF", "cheek": "#FDBA74",
        "ear_inner": "#FEF0F5", "accent": "#38BDF8",
        "headphone": "#475569", "headphone_pad": "#E2E8F0",
        "mic": "#FBBF24", "mic_body": "#475569",
        "scarf": "#38BDF8", "note": "#F472B6", "star": "#FBBF24",
    },
}

DEFAULT_THEME = "classic"

# ── 通用色 ──
C_EYE = "#2D2048"
C_EYE_HL = "#FFFFFF"
C_OUTLINE = "#2D2048"
C_MOUTH = "#2D2048"


# ═══════════════════════════════════════════════════════════════
# 共享 SVG defs (极简)
# ═══════════════════════════════════════════════════════════════

def _svg_defs() -> str:
    return """
<defs>
  <radialGradient id="bodyGrad" cx="42%" cy="30%" r="70%">
    <stop offset="0%" stop-color="{body_light}"/>
    <stop offset="60%" stop-color="{body}"/>
    <stop offset="100%" stop-color="{body_dark}"/>
  </radialGradient>
  <radialGradient id="blushGrad" cx="50%" cy="50%" r="50%">
    <stop offset="0%" stop-color="{cheek}" stop-opacity="0.7"/>
    <stop offset="60%" stop-color="{cheek}" stop-opacity="0.25"/>
    <stop offset="100%" stop-color="{cheek}" stop-opacity="0"/>
  </radialGradient>
  <filter id="shadow" x="-25%" y="-20%" width="150%" height="140%">
    <feDropShadow dx="0" dy="4" stdDeviation="4" flood-color="#000000" flood-opacity="0.12"/>
  </filter>
  <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
    <feGaussianBlur stdDeviation="2.5" result="blur"/>
    <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
</defs>"""


# ═══════════════════════════════════════════════════════════════
# 脸部部件 —— 极简大眼 + 超大腮红(>眼睛!)
# ═══════════════════════════════════════════════════════════════

def _blush(cx_l: float, cx_r: float, cy: float, r: float) -> str:
    return (
        f'<circle cx="{cx_l:.0f}" cy="{cy:.0f}" r="{r:.0f}" fill="url(#blushGrad)"/>\n'
        f'<circle cx="{cx_r:.0f}" cy="{cy:.0f}" r="{r:.0f}" fill="url(#blushGrad)"/>'
    )


def _eyes_idle(cx_l: float, cx_r: float, cy: float, r: float) -> str:
    """大圆眼 + 2个高光 (主高光 + 副高光)"""
    hl1x = cx_l + r * 0.35; hl1y = cy - r * 0.3
    hl2x = cx_l - r * 0.15; hl2y = cy + r * 0.2
    return (
        f'<circle cx="{cx_l:.0f}" cy="{cy:.0f}" r="{r:.0f}" fill="{C_EYE}"/>\n'
        f'<circle cx="{cx_r:.0f}" cy="{cy:.0f}" r="{r:.0f}" fill="{C_EYE}"/>\n'
        f'<circle cx="{hl1x:.1f}" cy="{hl1y:.1f}" r="{r*0.38:.1f}" fill="{C_EYE_HL}"/>\n'
        f'<circle cx="{cx_r+r*0.35:.1f}" cy="{hl1y:.1f}" r="{r*0.38:.1f}" fill="{C_EYE_HL}"/>\n'
        f'<circle cx="{hl2x:.1f}" cy="{hl2y:.1f}" r="{r*0.18:.1f}" fill="{C_EYE_HL}" opacity="0.7"/>\n'
        f'<circle cx="{cx_r-r*0.15:.1f}" cy="{hl2y:.1f}" r="{r*0.18:.1f}" fill="{C_EYE_HL}" opacity="0.7"/>'
    )


def _eyes_singing(cx_l: float, cx_r: float, cy: float, r: float) -> str:
    """陶醉闭眼 — 下弯弧"""
    return (
        f'<path d="M{cx_l-r:.0f} {cy:.0f} Q{cx_l:.0f} {cy-r*0.7:.0f} {cx_l+r:.0f} {cy:.0f}" '
        f'stroke="{C_EYE}" stroke-width="3" fill="none" stroke-linecap="round"/>\n'
        f'<path d="M{cx_r-r:.0f} {cy:.0f} Q{cx_r:.0f} {cy-r*0.7:.0f} {cx_r+r:.0f} {cy:.0f}" '
        f'stroke="{C_EYE}" stroke-width="3" fill="none" stroke-linecap="round"/>'
    )


def _eyes_happy(cx_l: float, cx_r: float, cy: float, r: float) -> str:
    """开心眯眼 — 上弯弧 (^_^)"""
    return (
        f'<path d="M{cx_l-r:.0f} {cy+2:.0f} Q{cx_l:.0f} {cy-r*0.65:.0f} {cx_l+r:.0f} {cy+2:.0f}" '
        f'stroke="{C_EYE}" stroke-width="3" fill="none" stroke-linecap="round"/>\n'
        f'<path d="M{cx_r-r:.0f} {cy+2:.0f} Q{cx_r:.0f} {cy-r*0.65:.0f} {cx_r+r:.0f} {cy+2:.0f}" '
        f'stroke="{C_EYE}" stroke-width="3" fill="none" stroke-linecap="round"/>'
    )


def _eyes_thinking(cx_l: float, cx_r: float, cy: float, r: float) -> str:
    """思考 — 瞳孔上移"""
    return (
        f'<circle cx="{cx_l:.0f}" cy="{cy:.0f}" r="{r:.0f}" fill="{C_EYE}"/>\n'
        f'<circle cx="{cx_r:.0f}" cy="{cy:.0f}" r="{r:.0f}" fill="{C_EYE}"/>\n'
        f'<circle cx="{cx_l+r*0.2:.1f}" cy="{cy-r*0.35:.1f}" r="{r*0.3:.1f}" fill="{C_EYE_HL}"/>\n'
        f'<circle cx="{cx_r+r*0.2:.1f}" cy="{cy-r*0.35:.1f}" r="{r*0.3:.1f}" fill="{C_EYE_HL}"/>\n'
        f'<circle cx="{cx_l-r*0.2:.1f}" cy="{cy-r*0.5:.1f}" r="{r*0.15:.1f}" fill="{C_EYE_HL}" opacity="0.5"/>\n'
        f'<circle cx="{cx_r-r*0.2:.1f}" cy="{cy-r*0.5:.1f}" r="{r*0.15:.1f}" fill="{C_EYE_HL}" opacity="0.5"/>'
    )


def _eyes_surprised(cx_l: float, cx_r: float, cy: float, r: float) -> str:
    """惊讶 — 眼睛更大"""
    return _eyes_idle(cx_l, cx_r, cy - 1, r * 1.12)


def _eyes_loved(cx_l: float, cx_r: float, cy: float, r: float) -> str:
    """被抚摸 — 极度开心眯眼 + 爱心瞳 (♥‿♥)"""
    return (
        # 眯眼弧
        f'<path d="M{cx_l-r:.0f} {cy+2:.0f} Q{cx_l:.0f} {cy-r*0.6:.0f} {cx_l+r:.0f} {cy+2:.0f}" '
        f'stroke="{C_EYE}" stroke-width="2.8" fill="none" stroke-linecap="round"/>\n'
        f'<path d="M{cx_r-r:.0f} {cy+2:.0f} Q{cx_r:.0f} {cy-r*0.6:.0f} {cx_r+r:.0f} {cy+2:.0f}" '
        f'stroke="{C_EYE}" stroke-width="2.8" fill="none" stroke-linecap="round"/>\n'
        # 爱心装饰
        f'<text x="{cx_l-1:.0f}" y="{cy-r*0.3:.0f}" font-size="{r*0.7:.0f}" text-anchor="middle" '
        f'fill="{C_EYE_HL}" opacity="0.6">♥</text>\n'
        f'<text x="{cx_r-1:.0f}" y="{cy-r*0.3:.0f}" font-size="{r*0.7:.0f}" text-anchor="middle" '
        f'fill="{C_EYE_HL}" opacity="0.6">♥</text>'
    )


# ── 嘴巴 ──

def _mouth_smile(cx: float, cy: float) -> str:
    """小小微笑 (侧3)"""
    return (
        f'<path d="M{cx-6:.0f} {cy:.0f} Q{cx-3:.0f} {cy+6:.0f} {cx:.0f} {cy+1:.0f} '
        f'Q{cx+3:.0f} {cy+6:.0f} {cx+6:.0f} {cy:.0f}" '
        f'stroke="{C_MOUTH}" stroke-width="2" fill="none" stroke-linecap="round"/>'
    )


def _mouth_open(cx: float, cy: float) -> str:
    """张嘴 (唱歌/开心)"""
    return (
        f'<ellipse cx="{cx:.0f}" cy="{cy+4:.0f}" rx="7" ry="9" fill="{C_MOUTH}"/>\n'
        f'<ellipse cx="{cx:.0f}" cy="{cy-1:.0f}" rx="4.5" ry="4" fill="#FF8FA3"/>'
    )


def _mouth_surprised(cx: float, cy: float) -> str:
    """惊讶小圆嘴"""
    return (
        f'<circle cx="{cx:.0f}" cy="{cy+2:.0f}" r="7" fill="{C_MOUTH}"/>\n'
        f'<circle cx="{cx:.0f}" cy="{cy-1:.0f}" r="3.5" fill="#FF8FA3"/>'
    )


def _mouth_loved(cx: float, cy: float) -> str:
    """被抚摸 — 大开心张嘴"""
    return _mouth_open(cx, cy)


# ═══════════════════════════════════════════════════════════════
# 麦麦 V5 — 音乐小猫 (皮卡丘比例)
#   超大圆头 + 大三角耳 + 圆耳机 + 小巧身体 (头身重叠)
# ═══════════════════════════════════════════════════════════════

def _maimai_body() -> str:
    return """
<!-- 地面阴影 -->
<ellipse cx="200" cy="365" rx="50" ry="8" fill="#00000008"/>
<!-- 后脚 (紧贴身体底部, 无缝) -->
<ellipse cx="172" cy="340" rx="14" ry="10" fill="{body_dark}"/>
<ellipse cx="228" cy="340" rx="14" ry="10" fill="{body_dark}"/>
<!-- 身体 (头身重叠 ~24px: 头底216, 体顶192) -->
<ellipse cx="200" cy="264" rx="62" ry="72" fill="url(#bodyGrad)" filter="url(#shadow)"/>
<!-- 肚皮 -->
<ellipse cx="200" cy="278" rx="38" ry="44" fill="{belly}" opacity="0.6"/>
<!-- 前爪 (圆手套) -->
<ellipse cx="148" cy="248" rx="12" ry="16" fill="{body}" transform="rotate(-15 148 248)"/>
<ellipse cx="252" cy="248" rx="12" ry="16" fill="{body}" transform="rotate(15 252 248)"/>
<!-- 尾巴 (卷曲) -->
<path d="M258 288 Q290 268 295 234 Q298 210 288 202" stroke="{body}" stroke-width="9" fill="none" stroke-linecap="round"/>
<circle cx="288" cy="202" r="5.5" fill="{body_light}"/>"""


def _maimai_head() -> str:
    return """
<!-- 头部 (超大圆头, 中心 y=138) -->
<ellipse cx="200" cy="138" rx="88" ry="78" fill="url(#bodyGrad)"/>
<!-- 猫耳 (大三角, 圆角) -->
<path d="M122 120 L108 42 L156 90" fill="{body}" stroke="{body_dark}" stroke-width="2" stroke-linejoin="round"/>
<path d="M128 112 L118 56 L152 90" fill="{ear_inner}"/>
<path d="M278 120 L292 42 L244 90" fill="{body}" stroke="{body_dark}" stroke-width="2" stroke-linejoin="round"/>
<path d="M272 112 L282 56 L248 90" fill="{ear_inner}"/>
<!-- 短胡须 -->
<line x1="104" y1="138" x2="132" y2="145" stroke="{body_dark}" stroke-width="1.2" opacity="0.35" stroke-linecap="round"/>
<line x1="101" y1="148" x2="130" y2="151" stroke="{body_dark}" stroke-width="1.2" opacity="0.35" stroke-linecap="round"/>
<line x1="296" y1="138" x2="268" y2="145" stroke="{body_dark}" stroke-width="1.2" opacity="0.35" stroke-linecap="round"/>
<line x1="299" y1="148" x2="270" y2="151" stroke="{body_dark}" stroke-width="1.2" opacity="0.35" stroke-linecap="round"/>"""


def _maimai_extras() -> str:
    return """
<!-- 圆耳机 (两侧大圆) -->
<circle cx="114" cy="105" r="20" fill="{headphone_pad}"/>
<circle cx="114" cy="105" r="12" fill="{headphone}"/>
<circle cx="286" cy="105" r="20" fill="{headphone_pad}"/>
<circle cx="286" cy="105" r="12" fill="{headphone}"/>
<!-- 耳机梁 -->
<path d="M134 105 Q200 32 266 105" stroke="{headphone}" stroke-width="5" fill="none" stroke-linecap="round"/>
<!-- 领结 (头身交界处) -->
<path d="M184 204 L200 212 L216 204 L200 196 Z" fill="{accent}"/>
<circle cx="200" cy="204" r="4.5" fill="{star}"/>
<!-- 麦克风 -->
<rect x="268" y="240" width="7" height="40" rx="3.5" fill="{mic_body}" transform="rotate(14 271 260)"/>
<ellipse cx="276" cy="234" rx="11" ry="15" fill="{mic}" transform="rotate(14 276 234)" filter="url(#glow)"/>
<path d="M258 224 Q272 216 276 232" stroke="{body}" stroke-width="10" fill="none" stroke-linecap="round"/>"""

# 麦麦面部: 眼睛 r=9, 腮红 r=15 → 腮红>>眼睛!
M_FACE = {"cx_l": 162, "cx_r": 238, "cy_eye": 132, "r_eye": 9,
          "cy_blush": 156, "r_blush": 15, "cx_mouth": 200, "cy_mouth": 164}


# ═══════════════════════════════════════════════════════════════
# 团团 V5 — 豆豆小熊 (松弛熊风格)
#   超大圆头 + 迷你圆耳 + 圆豆身体 + 蝴蝶结
# ═══════════════════════════════════════════════════════════════

def _tuantuan_body() -> str:
    return """
<!-- 地面阴影 -->
<ellipse cx="200" cy="370" rx="55" ry="9" fill="#00000006"/>
<!-- 后脚掌 (紧贴身体底部, 无缝) -->
<ellipse cx="168" cy="360" rx="18" ry="11" fill="{body_dark}"/>
<ellipse cx="232" cy="360" rx="18" ry="11" fill="{body_dark}"/>
<!-- 身体 (头身重叠 ~24px: 头底222, 体顶198) -->
<ellipse cx="200" cy="276" rx="68" ry="78" fill="url(#bodyGrad)" filter="url(#shadow)"/>
<!-- 肚皮 -->
<ellipse cx="200" cy="292" rx="43" ry="48" fill="{belly}" opacity="0.6"/>
<!-- 小短手 -->
<ellipse cx="136" cy="264" rx="14" ry="20" fill="{body}" transform="rotate(-18 136 264)"/>
<ellipse cx="264" cy="264" rx="14" ry="20" fill="{body}" transform="rotate(18 264 264)"/>"""


def _tuantuan_head() -> str:
    return """
<!-- 头部 (最大圆脸, 中心 y=140) -->
<ellipse cx="200" cy="140" rx="90" ry="82" fill="url(#bodyGrad)"/>
<!-- 迷你圆耳 -->
<circle cx="138" cy="82" r="20" fill="{body_dark}"/>
<circle cx="138" cy="82" r="12" fill="{body_light}"/>
<circle cx="262" cy="82" r="20" fill="{body_dark}"/>
<circle cx="262" cy="82" r="12" fill="{body_light}"/>"""


def _tuantuan_extras() -> str:
    return """
<!-- 蝴蝶结 (头身交界处) -->
<path d="M180 192 L200 200 L220 192 L200 184 Z" fill="{accent}"/>
<circle cx="200" cy="192" r="5" fill="{body_dark}"/>
<!-- 小音符 -->
<g transform="translate(288 222) rotate(6)" filter="url(#glow)" opacity="0.7">
  <ellipse cx="0" cy="0" rx="7" ry="5" fill="{note}"/>
  <rect x="6" y="-20" width="3" height="20" rx="1.5" fill="{note}"/>
</g>"""

T_FACE = {"cx_l": 162, "cx_r": 238, "cy_eye": 134, "r_eye": 8.5,
          "cy_blush": 158, "r_blush": 15, "cx_mouth": 200, "cy_mouth": 168}


# ═══════════════════════════════════════════════════════════════
# 音音 V5 — 破壳小鸡 (单一体! 无头身分离!)
#   一个整体圆蛋形 + 蛋壳底座 + 羽冠 + 小翅膀
# ═══════════════════════════════════════════════════════════════

def _yinyin_body() -> str:
    """单一体: 整个小鸡是一个圆蛋形"""
    return """
<!-- 地面阴影 -->
<ellipse cx="200" cy="390" rx="55" ry="9" fill="#00000006"/>
<!-- 蛋壳底座 -->
<path d="M142 340 Q200 368 258 340" fill="#FFFEF5" stroke="#E8E4D0" stroke-width="2"/>
<path d="M142 340 L146 350 L154 342 L162 352 L170 342 L178 352 L186 342 L194 352 L200 338 L206 352 L214 342 L222 352 L230 342 L238 352 L246 342 L254 352 L258 340" fill="#FFFEF5" stroke="#E8E4D0" stroke-width="1.5"/>
<!-- 单一体身体 (头身融合, 一个大圆蛋) -->
<ellipse cx="200" cy="238" rx="76" ry="98" fill="url(#bodyGrad)" filter="url(#shadow)"/>
<!-- 肚皮高光 -->
<ellipse cx="200" cy="260" rx="46" ry="56" fill="{belly}" opacity="0.5"/>
<!-- 小翅膀 -->
<ellipse cx="128" cy="245" rx="14" ry="24" fill="{body}" transform="rotate(18 128 245)"/>
<ellipse cx="128" cy="248" rx="6" ry="12" fill="{body_light}" opacity="0.5" transform="rotate(18 128 248)"/>
<ellipse cx="272" cy="245" rx="14" ry="24" fill="{body}" transform="rotate(-18 272 245)"/>
<ellipse cx="272" cy="248" rx="6" ry="12" fill="{body_light}" opacity="0.5" transform="rotate(-18 272 248)"/>"""


def _yinyin_head() -> str:
    """头部融入身体, 只有羽冠和喙作为头部标记"""
    return """
<!-- 三羽冠 (头顶装饰) -->
<path d="M186 146 L176 100 L194 138" fill="{accent}" stroke="{body_dark}" stroke-width="1.5" stroke-linejoin="round"/>
<path d="M200 140 L200 90 L208 136" fill="{body_light}" stroke="{body_dark}" stroke-width="1.5" stroke-linejoin="round"/>
<path d="M214 146 L224 100 L206 138" fill="{accent}" stroke="{body_dark}" stroke-width="1.5" stroke-linejoin="round"/>
<!-- 小喙 -->
<path d="M194 198 L184 204 L194 209" fill="{accent}" stroke="{body_dark}" stroke-width="1.5" stroke-linejoin="round"/>"""


def _yinyin_extras() -> str:
    return """
<!-- 蛋壳纹理 -->
<path d="M155 355 Q160 362 158 368" stroke="{body_dark}" stroke-width="1" fill="none" opacity="0.1"/>
<path d="M242 358 Q238 365 240 370" stroke="{body_dark}" stroke-width="1" fill="none" opacity="0.1"/>"""

# 音音面部: 眼睛在身体上半部, 腮红>>眼睛!
Y_FACE = {"cx_l": 166, "cx_r": 234, "cy_eye": 180, "r_eye": 10,
          "cy_blush": 208, "r_blush": 16, "cx_mouth": 196, "cy_mouth": 210}


# ═══════════════════════════════════════════════════════════════
# 球球 V5 — 水滴史莱姆 (百变怪极简风)
#   单一水滴形 + 超大眼 + 超大腮红 + 呆毛
# ═══════════════════════════════════════════════════════════════

def _qiuqiu_body() -> str:
    return """
<!-- 地面阴影 -->
<ellipse cx="200" cy="392" rx="70" ry="12" fill="#00000005"/>
<!-- 底部小凸起 (蠕动) -->
<ellipse cx="158" cy="384" rx="14" ry="6" fill="{body}" opacity="0.5"/>
<ellipse cx="242" cy="384" rx="14" ry="6" fill="{body}" opacity="0.5"/>
<ellipse cx="200" cy="388" rx="18" ry="7" fill="{body}" opacity="0.5"/>
<!-- 单一主体 (水滴形) -->
<ellipse cx="200" cy="252" rx="88" ry="120" fill="url(#bodyGrad)" filter="url(#shadow)"/>
<!-- 肚皮高光 -->
<ellipse cx="200" cy="290" rx="54" ry="68" fill="{belly}" opacity="0.45"/>
<!-- 顶部高光反射 -->
<ellipse cx="178" cy="172" rx="24" ry="10" fill="#FFFFFF" opacity="0.1" transform="rotate(-18 178 172)"/>"""


def _qiuqiu_head() -> str:
    return ""

def _qiuqiu_extras() -> str:
    return """
<!-- 呆毛 -->
<path d="M200 132 Q202 114 210 130" fill="{body}" stroke="{body_dark}" stroke-width="1.8" stroke-linecap="round"/>
<!-- 魔法光点 -->
<circle cx="288" cy="192" r="4.5" fill="{body_light}" opacity="0.4" filter="url(#glow)"/>
<circle cx="305" cy="216" r="2.8" fill="{body_light}" opacity="0.25"/>
<circle cx="115" cy="202" r="3.2" fill="{body_light}" opacity="0.3" filter="url(#glow)"/>
<circle cx="296" cy="172" r="2.2" fill="{star}" opacity="0.3"/>
<circle cx="106" cy="232" r="2" fill="{star}" opacity="0.2"/>"""

# 球球面部: 超大眼 + 更大腮红!
Q_FACE = {"cx_l": 158, "cx_r": 242, "cy_eye": 218, "r_eye": 11,
          "cy_blush": 254, "r_blush": 18, "cx_mouth": 200, "cy_mouth": 260}


# ═══════════════════════════════════════════════════════════════
# 绵绵 V5 — 垂耳兔兔 (伊布长耳风格)
#   圆脸 + 一耳垂一耳立 + 棉花尾 + 领巾
# ═══════════════════════════════════════════════════════════════

def _mianmian_body() -> str:
    return """
<!-- 地面阴影 -->
<ellipse cx="200" cy="370" rx="42" ry="7" fill="#00000005"/>
<!-- 脚掌 (紧贴身体底部, 无缝) -->
<ellipse cx="178" cy="350" rx="13" ry="9" fill="{body_dark}"/>
<ellipse cx="222" cy="350" rx="13" ry="9" fill="{body_dark}"/>
<!-- 身体 (头身重叠 ~22px: 头底218, 体顶196) -->
<ellipse cx="200" cy="270" rx="56" ry="74" fill="url(#bodyGrad)" filter="url(#shadow)"/>
<!-- 肚皮 -->
<ellipse cx="200" cy="284" rx="33" ry="42" fill="{belly}" opacity="0.6"/>
<!-- 棉花尾 -->
<circle cx="268" cy="300" r="15" fill="{body_light}" filter="url(#shadow)"/>
<circle cx="266" cy="297" r="9" fill="#FFFFFF" opacity="0.65"/>
<circle cx="272" cy="295" r="4.5" fill="#FFFFFF" opacity="0.4"/>"""


def _mianmian_head() -> str:
    return """
<!-- 头部 (圆脸, 中心 y=148) -->
<ellipse cx="200" cy="148" rx="78" ry="70" fill="url(#bodyGrad)"/>
<!-- 左耳 (完全垂落, 长!) -->
<path d="M158 100 Q135 48 132 22 Q130 8 143 10 Q156 12 152 38 Q147 72 150 108"
      fill="{body}" stroke="{body_dark}" stroke-width="2.2" stroke-linejoin="round"/>
<path d="M155 96 Q138 50 135 28 Q133 16 143 18 Q152 20 149 40 Q145 70 148 100"
      fill="{ear_inner}"/>
<!-- 右耳 (竖立, 像伊布) -->
<ellipse cx="240" cy="62" rx="13" ry="50" fill="{body}" stroke="{body_dark}" stroke-width="2.2" transform="rotate(8 240 62)"/>
<ellipse cx="240" cy="62" rx="7" ry="40" fill="{ear_inner}" transform="rotate(8 240 62)"/>
<!-- 耳根小饰 -->
<circle cx="246" cy="50" r="5" fill="{accent}" opacity="0.7"/>"""


def _mianmian_extras() -> str:
    return """
<!-- 领巾 (头身交界处) -->
<path d="M164 196 Q200 207 236 196" stroke="{scarf}" stroke-width="6" fill="none" stroke-linecap="round" opacity="0.7"/>
<path d="M230 194 Q236 222 232 240 Q228 218 222 206" fill="{scarf}" opacity="0.7"/>"""

# 绵绵面部: 眼睛+大腮红
N_FACE = {"cx_l": 168, "cx_r": 232, "cy_eye": 140, "r_eye": 9,
          "cy_blush": 162, "r_blush": 14, "cx_mouth": 200, "cy_mouth": 168}


# ═══════════════════════════════════════════════════════════════
# 装饰元素
# ═══════════════════════════════════════════════════════════════

def _singing_notes() -> str:
    return """
<g transform="translate(300 95) rotate(12)" filter="url(#glow)">
  <ellipse cx="0" cy="0" rx="8" ry="6" fill="{note}"/>
  <rect x="7" y="-30" width="3" height="30" rx="1.5" fill="{note}"/>
  <path d="M7 -30 Q18 -32 20 -18" stroke="{note}" stroke-width="2.5" fill="none" stroke-linecap="round"/>
</g>
<g transform="translate(325 52) rotate(-8)" filter="url(#glow)">
  <ellipse cx="0" cy="0" rx="7" ry="5" fill="{star}"/>
  <rect x="6" y="-24" width="3" height="24" rx="1.5" fill="{star}"/>
</g>
<g transform="translate(65 68) rotate(-15)" opacity="0.4">
  <ellipse cx="0" cy="0" rx="5.5" ry="3.5" fill="{note}"/>
  <rect x="4.5" y="-18" width="2" height="18" rx="1" fill="{note}"/>
</g>"""


def _happy_stars() -> str:
    return """
<polygon points="290,78 293,92 308,92 296,100 300,114 290,106 280,114 284,100 272,92 287,92"
         fill="{star}" filter="url(#glow)" transform="scale(0.7) translate(120 15)"/>
<polygon points="108,70 110,80 120,80 112,86 115,95 108,89 101,95 104,86 96,80 106,80"
         fill="{star}" opacity="0.4" transform="scale(0.5) translate(75 22)"/>
<circle cx="310" cy="60" r="3" fill="{star}" opacity="0.4"/>
<circle cx="75" cy="55" r="2.5" fill="{star}" opacity="0.3"/>"""


def _thinking_dots() -> str:
    return """
<circle cx="280" cy="82" r="7" fill="{body_light}" opacity="0.5"/>
<circle cx="298" cy="64" r="5" fill="{body_light}" opacity="0.32"/>
<circle cx="310" cy="50" r="3.2" fill="{body_light}" opacity="0.18"/>"""


def _idle_note() -> str:
    return """
<g transform="translate(300 68) rotate(6)" opacity="0.22">
  <ellipse cx="0" cy="0" rx="5.5" ry="3.5" fill="{note}"/>
  <rect x="4.5" y="-16" width="2" height="16" rx="1" fill="{note}"/>
</g>"""


def _surprise_marks() -> str:
    return """
<text x="266" y="62" font-size="28" font-weight="bold" fill="{star}"
      filter="url(#glow)" font-family="Arial, sans-serif">!</text>
<text x="298" y="44" font-size="20" font-weight="bold" fill="{star}"
      opacity="0.45" font-family="Arial, sans-serif">!</text>"""


def _heart_shower() -> str:
    """被抚摸 — 爱心雨 (大小爱心飘浮)"""
    return """
<g filter="url(#glow)">
  <text x="85" y="50" font-size="18" fill="{accent}" opacity="0.85" font-family="Arial">♥</text>
  <text x="290" y="40" font-size="22" fill="{accent}" opacity="0.8" font-family="Arial">♥</text>
  <text x="310" y="70" font-size="14" fill="{cheek}" opacity="0.7" font-family="Arial">♥</text>
  <text x="65" y="72" font-size="15" fill="{cheek}" opacity="0.65" font-family="Arial">♥</text>
  <text x="275" y="55" font-size="12" fill="{star}" opacity="0.55" font-family="Arial">♥</text>
  <text x="95" y="36" font-size="10" fill="{star}" opacity="0.45" font-family="Arial">♥</text>
  <text x="255" y="30" font-size="9" fill="{accent}" opacity="0.4" font-family="Arial">♥</text>
</g>"""


# ═══════════════════════════════════════════════════════════════
# 角色部件注册表
# ═══════════════════════════════════════════════════════════════

_CHAR_PARTS = {
    "maimai":   {"body": _maimai_body, "head": _maimai_head, "extras": _maimai_extras, "face": M_FACE},
    "tuantuan": {"body": _tuantuan_body, "head": _tuantuan_head, "extras": _tuantuan_extras, "face": T_FACE},
    "yinyin":   {"body": _yinyin_body, "head": _yinyin_head, "extras": _yinyin_extras, "face": Y_FACE},
    "qiuqiu":   {"body": _qiuqiu_body, "head": _qiuqiu_head, "extras": _qiuqiu_extras, "face": Q_FACE},
    "mianmian": {"body": _mianmian_body, "head": _mianmian_head, "extras": _mianmian_extras, "face": N_FACE},
}


# ═══════════════════════════════════════════════════════════════
# 组装
# ═══════════════════════════════════════════════════════════════

def _assemble(parts: dict, f: dict, eyes_tpl: str, mouth_tpl: str,
              blush_tpl: str, extra_tpl: str) -> str:
    return "".join([
        _svg_defs(),
        parts["body"](),
        parts["head"](),
        eyes_tpl,
        blush_tpl,
        parts["extras"](),
        mouth_tpl,
        extra_tpl,
    ])


def get_svg(expression: str = "idle", theme: str = DEFAULT_THEME) -> str:
    expression = expression.lower()
    palette = THEMES.get(theme, THEMES[DEFAULT_THEME])
    character = palette.get("character", "maimai")
    reg = _CHAR_PARTS.get(character, _CHAR_PARTS["maimai"])
    parts_dict = {"body": reg["body"], "head": reg["head"], "extras": reg["extras"]}
    f = reg["face"]

    eyes_map = {
        "idle":      lambda: _eyes_idle(f["cx_l"], f["cx_r"], f["cy_eye"], f["r_eye"]),
        "singing":   lambda: _eyes_singing(f["cx_l"], f["cx_r"], f["cy_eye"], f["r_eye"]),
        "thinking":  lambda: _eyes_thinking(f["cx_l"], f["cx_r"], f["cy_eye"], f["r_eye"]),
        "happy":     lambda: _eyes_happy(f["cx_l"], f["cx_r"], f["cy_eye"], f["r_eye"]),
        "surprised": lambda: _eyes_surprised(f["cx_l"], f["cx_r"], f["cy_eye"], f["r_eye"]),
        "loved":     lambda: _eyes_loved(f["cx_l"], f["cx_r"], f["cy_eye"], f["r_eye"]),
    }
    mouth_map = {
        "idle":      lambda: _mouth_smile(f["cx_mouth"], f["cy_mouth"]),
        "singing":   lambda: _mouth_open(f["cx_mouth"], f["cy_mouth"]),
        "thinking":  lambda: _mouth_smile(f["cx_mouth"], f["cy_mouth"]),
        "happy":     lambda: _mouth_open(f["cx_mouth"], f["cy_mouth"]),
        "surprised": lambda: _mouth_surprised(f["cx_mouth"], f["cy_mouth"]),
        "loved":     lambda: _mouth_loved(f["cx_mouth"], f["cy_mouth"]),
    }
    extras_map = {
        "idle":      _idle_note(),
        "singing":   _singing_notes(),
        "happy":     _happy_stars(),
        "thinking":  _thinking_dots(),
        "surprised": _surprise_marks(),
        "loved":     _heart_shower(),
    }

    inner = _assemble(
        parts=parts_dict,
        f=f,
        eyes_tpl=eyes_map.get(expression, eyes_map["idle"])(),
        mouth_tpl=mouth_map.get(expression, mouth_map["idle"])(),
        blush_tpl=_blush(f["cx_l"], f["cx_r"], f["cy_blush"], f["r_blush"]),
        extra_tpl=extras_map.get(expression, ""),
    )
    inner = inner.format(**palette)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="400" height="400">
{inner}
</svg>"""


# ═══════════════════════════════════════════════════════════════
# CSS 动画
# ═══════════════════════════════════════════════════════════════

MASCOT_ANIMATION_CSS = """
.mindecho-mascot {
    position: relative; display: inline-block; cursor: pointer;
    transition: transform 0.3s ease; user-select: none;
}
.mindecho-mascot:hover { transform: scale(1.1); }
.mindecho-mascot:active { transform: scale(0.9); }

@keyframes mascot-breathe {
    0%, 100% { transform: translateY(0px); }
    50% { transform: translateY(-5px); }
}
.mindecho-mascot.idle { animation: mascot-breathe 2.8s ease-in-out infinite; }

@keyframes mascot-singing {
    0%, 100% { transform: translateY(0px) rotate(-2deg); }
    25% { transform: translateY(-4px) rotate(0deg); }
    50% { transform: translateY(0px) rotate(2deg); }
    75% { transform: translateY(-4px) rotate(0deg); }
}
.mindecho-mascot.singing { animation: mascot-singing 0.7s ease-in-out infinite; }

@keyframes mascot-thinking {
    0%, 100% { transform: translateX(0px); }
    30% { transform: translateX(-4px); }
    70% { transform: translateX(4px); }
}
.mindecho-mascot.thinking { animation: mascot-thinking 1.6s ease-in-out infinite; }

@keyframes mascot-happy {
    0%, 100% { transform: translateY(0px) scale(1); }
    30% { transform: translateY(-18px) scale(1.1); }
    60% { transform: translateY(-3px) scale(1.03); }
}
.mindecho-mascot.happy { animation: mascot-happy 0.5s ease-out; }

@keyframes mascot-pop-in {
    0% { transform: scale(0) rotate(-15deg); opacity: 0; }
    60% { transform: scale(1.2) rotate(3deg); opacity: 1; }
    100% { transform: scale(1) rotate(0deg); opacity: 1; }
}
.mindecho-mascot.pop-in { animation: mascot-pop-in 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) forwards; }

@keyframes note-float {
    0% { transform: translateY(0px) scale(1); opacity: 0.5; }
    50% { transform: translateY(-18px) scale(1.25); opacity: 1; }
    100% { transform: translateY(-30px) scale(0.7); opacity: 0; }
}

.mascot-speech-bubble {
    position: absolute; top: -65px; left: 50%; transform: translateX(-50%);
    background: #2a2a4a; color: #e0e0e0; border: 2px solid #5B3FD9;
    border-radius: 16px; padding: 8px 14px; font-size: 12px;
    font-family: "Microsoft YaHei", sans-serif; white-space: nowrap;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3); opacity: 0;
    transition: opacity 0.3s ease; pointer-events: none;
}
.mascot-speech-bubble::after {
    content: ''; position: absolute; bottom: -8px; left: 50%;
    transform: translateX(-50%);
    border-left: 8px solid transparent; border-right: 8px solid transparent;
    border-top: 8px solid #5B3FD9;
}
.mindecho-mascot:hover .mascot-speech-bubble { opacity: 1; }
"""


# ═══════════════════════════════════════════════════════════════
# 便捷接口
# ═══════════════════════════════════════════════════════════════

def save_svg(expression: str = "idle", theme: str = DEFAULT_THEME, path: str = ""):
    svg = get_svg(expression, theme)
    if not path:
        path = f"mindecho_mascot_{theme}_{expression}.svg"
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    return path


def get_all_expressions(theme: str = DEFAULT_THEME) -> dict[str, str]:
    return {expr: get_svg(expr, theme)
            for expr in ["idle", "singing", "thinking", "happy", "surprised"]}


def get_html_widget(expression: str = "idle", theme: str = DEFAULT_THEME,
                    size: int = 200) -> str:
    svg = get_svg(expression, theme)
    return f"""<div class="mindecho-mascot {expression} pop-in" style="width:{size}px;height:{size}px;">
  <div class="mascot-speech-bubble">需要帮助吗？</div>
  {svg.replace('<svg ', f'<svg width="{size}" height="{size}" ')}
</div>"""
