"""MindEcho AI 声乐教练桌宠 —— "麦麦" (MaiMai) SVG 形象

提供多表情/状态的 SVG 资源，支持动画切换。
表情: idle(默认微笑), singing(唱歌中), thinking(思考中), happy(开心), surprised(惊讶)
"""

# ═══════════════════════════════════════════════════════════════
# 基础调色盘
# ═══════════════════════════════════════════════════════════════

C_BODY = "#7C5CFC"         # 身体主色 - 温暖紫
C_BODY_LIGHT = "#A78BFA"   # 身体亮色
C_BODY_DARK = "#5B3FD9"    # 身体暗色
C_BELLY = "#E8E0FF"        # 肚皮浅紫白
C_EYE = "#1A1A2E"          # 眼睛深色
C_EYE_HIGHLIGHT = "#FFFFFF"  # 眼睛高光
C_CHEEK = "#FF6B9D"        # 腮红粉
C_MOUTH = "#5B3FD9"        # 嘴巴
C_HEADPHONE = "#3D3D5C"    # 耳机框架
C_HEADPHONE_PAD = "#FF6B9D"  # 耳机耳罩粉
C_MIC = "#FFD93D"          # 麦克风金色
C_MIC_BODY = "#3D3D5C"     # 麦克风手柄
C_NOTE = "#4ADE80"          # 音符绿色
C_STAR = "#FFD93D"         # 星星金色
C_SCARF = "#FF6B9D"        # 围巾粉
C_SHADOW = "#00000015"     # 阴影

# ═══════════════════════════════════════════════════════════════
# 通用定义 (SVG defs)
# ═══════════════════════════════════════════════════════════════

SVG_DEFS = """
<defs>
  <!-- 身体渐变 -->
  <radialGradient id="bodyGrad" cx="50%" cy="40%" r="60%">
    <stop offset="0%" stop-color="{body_light}"/>
    <stop offset="100%" stop-color="{body}"/>
  </radialGradient>

  <!-- 肚皮渐变 -->
  <radialGradient id="bellyGrad" cx="50%" cy="30%" r="50%">
    <stop offset="0%" stop-color="#FFFFFF"/>
    <stop offset="100%" stop-color="{belly}"/>
  </radialGradient>

  <!-- 阴影滤镜 -->
  <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
    <feDropShadow dx="0" dy="3" stdDeviation="4" flood-color="#000000" flood-opacity="0.2"/>
  </filter>

  <!-- 发光滤镜 -->
  <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
    <feGaussianBlur stdDeviation="3" result="blur"/>
    <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
</defs>
"""

# ═══════════════════════════════════════════════════════════════
# 身体部件模板
# ═══════════════════════════════════════════════════════════════

# 身体 (共享)
BODY = """
<!-- 阴影 -->
<ellipse cx="200" cy="385" rx="70" ry="12" fill="{shadow}"/>
<!-- 脚 -->
<ellipse cx="165" cy="375" rx="22" ry="14" fill="{body_dark}"/>
<ellipse cx="235" cy="375" rx="22" ry="14" fill="{body_dark}"/>
<!-- 身体 -->
<ellipse cx="200" cy="285" rx="85" ry="95" fill="url(#bodyGrad)" filter="url(#shadow)"/>
<!-- 肚皮 -->
<ellipse cx="200" cy="305" rx="55" ry="60" fill="url(#bellyGrad)"/>
"""

# 头部 (共享)
HEAD = """
<!-- 头部 -->
<ellipse cx="200" cy="160" rx="75" ry="65" fill="url(#bodyGrad)"/>
"""

# 耳机
HEADPHONE = """
<!-- 耳机头梁 -->
<path d="M145 100 Q 200 45 255 100" stroke="{headphone}" stroke-width="7" fill="none" stroke-linecap="round"/>
<!-- 左耳罩 -->
<rect x="118" y="120" width="28" height="45" rx="14" fill="{headphone_pad}"/>
<rect x="122" y="124" width="20" height="37" rx="10" fill="{headphone}"/>
<!-- 右耳罩 -->
<rect x="254" y="120" width="28" height="45" rx="14" fill="{headphone_pad}"/>
<rect x="258" y="124" width="20" height="37" rx="10" fill="{headphone}"/>
"""

# 眼睛 (idle - 正常睁眼)
EYES_IDLE = """
<ellipse cx="178" cy="150" rx="12" ry="14" fill="{eye}"/>
<ellipse cx="222" cy="150" rx="12" ry="14" fill="{eye}"/>
<circle cx="183" cy="145" r="5" fill="{eye_highlight}"/>
<circle cx="227" cy="145" r="5" fill="{eye_highlight}"/>
<circle cx="175" cy="153" r="2" fill="{eye_highlight}"/>
<circle cx="219" cy="153" r="2" fill="{eye_highlight}"/>
"""

# 眼睛 (singing - 闭眼陶醉)
EYES_SINGING = """
<path d="M166 150 Q178 138 190 150" stroke="{eye}" stroke-width="4" fill="none" stroke-linecap="round"/>
<path d="M210 150 Q222 138 234 150" stroke="{eye}" stroke-width="4" fill="none" stroke-linecap="round"/>
"""

# 眼睛 (thinking - 向上看)
EYES_THINKING = """
<ellipse cx="178" cy="148" rx="12" ry="14" fill="{eye}"/>
<ellipse cx="222" cy="148" rx="12" ry="14" fill="{eye}"/>
<circle cx="180" cy="142" r="4" fill="{eye_highlight}"/>
<circle cx="224" cy="142" r="4" fill="{eye_highlight}"/>
"""

# 眼睛 (happy - 眯眼笑)
EYES_HAPPY = """
<path d="M166 150 Q178 140 190 152" stroke="{eye}" stroke-width="4" fill="none" stroke-linecap="round"/>
<path d="M210 152 Q222 140 234 150" stroke="{eye}" stroke-width="4" fill="none" stroke-linecap="round"/>
"""

# 腮红
BLUSH = """
<circle cx="160" cy="162" r="10" fill="{cheek}" opacity="0.35"/>
<circle cx="240" cy="162" r="10" fill="{cheek}" opacity="0.35"/>
"""

# 嘴巴 (idle - 微笑)
MOUTH_IDLE = """
<path d="M188 172 Q200 182 212 172" stroke="{mouth}" stroke-width="3" fill="none" stroke-linecap="round"/>
"""

# 嘴巴 (singing - 张大唱歌)
MOUTH_SINGING = """
<ellipse cx="200" cy="178" rx="10" ry="14" fill="{body_dark}"/>
<ellipse cx="200" cy="174" rx="8" ry="6" fill="#FF8FA3"/>
"""

# 嘴巴 (happy - 开心张嘴笑)
MOUTH_HAPPY = """
<path d="M186 168 Q200 186 214 168" fill="{body_dark}"/>
<path d="M191 172 Q200 180 209 172" fill="#FF8FA3"/>
"""

# 嘴巴 (surprised - 圆形)
MOUTH_SURPRISED = """
<circle cx="200" cy="175" r="9" fill="{body_dark}"/>
"""

# 麦克风
MICROPHONE = """
<!-- 麦克风手柄 -->
<rect x="268" y="270" width="10" height="55" rx="5" fill="{mic_body}" transform="rotate(15 273 297)"/>
<!-- 麦克风头 -->
<ellipse cx="278" cy="265" rx="14" ry="18" fill="{mic}" transform="rotate(15 278 265)" filter="url(#glow)"/>
<!-- 麦克风网格 -->
<ellipse cx="278" cy="265" rx="10" ry="13" fill="none" stroke="{mic_body}" stroke-width="2" transform="rotate(15 278 265)"/>
<!-- 手臂 -->
<path d="M260 250 Q275 245 278 260" stroke="{body}" stroke-width="14" fill="none" stroke-linecap="round"/>
"""

# 围巾
SCARF = """
<path d="M165 190 Q200 200 235 190" stroke="{scarf}" stroke-width="10" fill="none" stroke-linecap="round"/>
<path d="M228 188 Q240 220 235 240 Q230 220 225 210" fill="{scarf}"/>
"""

# ═══════════════════════════════════════════════════════════════
# 表情组装
# ═══════════════════════════════════════════════════════════════


def _assemble(eyes: str, mouth: str, extra: str = "") -> str:
    """组装完整 SVG"""
    parts = [
        SVG_DEFS,
        BODY,
        HEAD,
        HEADPHONE,
        eyes,
        BLUSH,
        SCARF,
        mouth,
        MICROPHONE,
        extra,
    ]
    return "".join(parts)


# ═══════════════════════════════════════════════════════════════
# 5 种表情的完整 SVG
# ═══════════════════════════════════════════════════════════════


def get_svg(expression: str = "idle") -> str:
    """获取指定表情的完整 SVG

    Args:
        expression: "idle" | "singing" | "thinking" | "happy" | "surprised"

    Returns:
        完整的 SVG 字符串 (可直接渲染或保存为 .svg 文件)
    """

    expression = expression.lower()

    eyes_map = {
        "idle": EYES_IDLE,
        "singing": EYES_SINGING,
        "thinking": EYES_THINKING,
        "happy": EYES_HAPPY,
        "surprised": EYES_IDLE,  # surprised 用正常眼睛但嘴巴是圆的
    }
    mouth_map = {
        "idle": MOUTH_IDLE,
        "singing": MOUTH_SINGING,
        "thinking": MOUTH_IDLE,
        "happy": MOUTH_HAPPY,
        "surprised": MOUTH_SURPRISED,
    }

    eyes = eyes_map.get(expression, EYES_IDLE)
    mouth = mouth_map.get(expression, MOUTH_IDLE)

    # 额外装饰
    extras = {
        "singing": _singing_notes(),
        "happy": _happy_stars(),
        "thinking": _thinking_dots(),
        "idle": _idle_note(),
        "surprised": _surprise_marks(),
    }
    extra = extras.get(expression, "")

    inner = _assemble(eyes, mouth, extra)
    inner = inner.format(
        body=C_BODY, body_light=C_BODY_LIGHT, body_dark=C_BODY_DARK,
        belly=C_BELLY, eye=C_EYE, eye_highlight=C_EYE_HIGHLIGHT,
        cheek=C_CHEEK, mouth=C_MOUTH, headphone=C_HEADPHONE,
        headphone_pad=C_HEADPHONE_PAD, mic=C_MIC, mic_body=C_MIC_BODY,
        note=C_NOTE, star=C_STAR, scarf=C_SCARF, shadow=C_SHADOW,
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="400" height="400">
{inner}
</svg>"""


# ═══════════════════════════════════════════════════════════════
# 装饰元素
# ═══════════════════════════════════════════════════════════════


def _singing_notes() -> str:
    return """
<!-- 音符 1 -->
<g transform="translate(290 100) rotate(15)" filter="url(#glow)">
  <ellipse cx="0" cy="0" rx="8" ry="6" fill="{note}"/>
  <rect x="7" y="-28" width="3" height="28" rx="2" fill="{note}"/>
  <path d="M7 -28 Q18 -30 20 -18" stroke="{note}" stroke-width="3" fill="none"/>
</g>
<!-- 音符 2 -->
<g transform="translate(310 60) rotate(-10)" filter="url(#glow)">
  <ellipse cx="0" cy="0" rx="7" ry="5" fill="{star}"/>
  <rect x="6" y="-24" width="3" height="24" rx="2" fill="{star}"/>
</g>
<!-- 音符 3 -->
<g transform="translate(80 80) rotate(-15)">
  <ellipse cx="0" cy="0" rx="6" ry="4" fill="{note}" opacity="0.6"/>
  <rect x="5" y="-20" width="2" height="20" rx="1" fill="{note}" opacity="0.6"/>
</g>
"""


def _happy_stars() -> str:
    return """
<!-- 星星 -->
<polygon points="280,90 283,100 293,100 285,106 288,116 280,110 272,116 275,106 267,100 277,100" fill="{star}" filter="url(#glow)" transform="scale(0.8) translate(60 10)"/>
<polygon points="120,80 122,87 129,87 123,91 125,98 120,94 115,98 117,91 111,87 118,87" fill="{star}" opacity="0.6" transform="scale(0.6) translate(70 20)"/>
"""


def _thinking_dots() -> str:
    return """
<circle cx="270" cy="100" r="6" fill="{body_light}" opacity="0.7"/>
<circle cx="285" cy="80" r="4" fill="{body_light}" opacity="0.5"/>
<circle cx="295" cy="65" r="3" fill="{body_light}" opacity="0.3"/>
"""


def _idle_note() -> str:
    return """
<g transform="translate(290 85) rotate(10)" opacity="0.4">
  <ellipse cx="0" cy="0" rx="6" ry="4" fill="{note}"/>
  <rect x="5" y="-18" width="2" height="18" rx="1" fill="{note}"/>
</g>
"""


def _surprise_marks() -> str:
    return """
<text x="260" y="80" font-size="28" font-weight="bold" fill="{star}" filter="url(#glow)">!</text>
<text x="285" y="65" font-size="20" font-weight="bold" fill="{star}" opacity="0.6">!</text>
"""


# ═══════════════════════════════════════════════════════════════
# 短动画 CSS
# ═══════════════════════════════════════════════════════════════


MASCOT_ANIMATION_CSS = """
/* 桌宠容器 */
.mindecho-mascot {
    position: relative;
    display: inline-block;
    cursor: pointer;
    transition: transform 0.3s ease;
    user-select: none;
}
.mindecho-mascot:hover {
    transform: scale(1.08);
}
.mindecho-mascot:active {
    transform: scale(0.95);
}

/* 呼吸动画 */
@keyframes mascot-breathe {
    0%, 100% { transform: translateY(0px); }
    50% { transform: translateY(-4px); }
}
.mindecho-mascot.idle {
    animation: mascot-breathe 3s ease-in-out infinite;
}

/* 唱歌摇摆 */
@keyframes mascot-singing {
    0%, 100% { transform: translateY(0px) rotate(-2deg); }
    25% { transform: translateY(-3px) rotate(0deg); }
    50% { transform: translateY(0px) rotate(2deg); }
    75% { transform: translateY(-3px) rotate(0deg); }
}
.mindecho-mascot.singing {
    animation: mascot-singing 0.8s ease-in-out infinite;
}

/* 思考晃动 */
@keyframes mascot-thinking {
    0%, 100% { transform: translateX(0px); }
    25% { transform: translateX(-3px); }
    75% { transform: translateX(3px); }
}
.mindecho-mascot.thinking {
    animation: mascot-thinking 2s ease-in-out infinite;
}

/* 开心跳跃 */
@keyframes mascot-happy {
    0%, 100% { transform: translateY(0px) scale(1); }
    30% { transform: translateY(-10px) scale(1.05); }
    60% { transform: translateY(-3px) scale(1.02); }
}
.mindecho-mascot.happy {
    animation: mascot-happy 0.6s ease-out;
}

/* 弹出出现 */
@keyframes mascot-pop-in {
    0% { transform: scale(0) rotate(-15deg); opacity: 0; }
    60% { transform: scale(1.15) rotate(3deg); opacity: 1; }
    100% { transform: scale(1) rotate(0deg); opacity: 1; }
}
.mindecho-mascot.pop-in {
    animation: mascot-pop-in 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
}

/* 音符浮动 */
@keyframes note-float {
    0% { transform: translateY(0px) scale(1); opacity: 0.6; }
    50% { transform: translateY(-15px) scale(1.2); opacity: 1; }
    100% { transform: translateY(-25px) scale(0.8); opacity: 0; }
}

/* 说话气泡 */
.mascot-speech-bubble {
    position: absolute;
    top: -60px;
    left: 50%;
    transform: translateX(-50%);
    background: #2a2a4a;
    color: #e0e0e0;
    border: 2px solid #5B3FD9;
    border-radius: 16px;
    padding: 8px 14px;
    font-size: 12px;
    font-family: "Microsoft YaHei", sans-serif;
    white-space: nowrap;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    opacity: 0;
    transition: opacity 0.3s ease;
    pointer-events: none;
}
.mascot-speech-bubble::after {
    content: '';
    position: absolute;
    bottom: -8px;
    left: 50%;
    transform: translateX(-50%);
    border-left: 8px solid transparent;
    border-right: 8px solid transparent;
    border-top: 8px solid #5B3FD9;
}
.mindecho-mascot:hover .mascot-speech-bubble {
    opacity: 1;
}
"""


# ═══════════════════════════════════════════════════════════════
# 便捷接口
# ═══════════════════════════════════════════════════════════════


def save_svg(expression: str = "idle", path: str = ""):
    """保存 SVG 到文件"""
    svg = get_svg(expression)
    if not path:
        path = f"mindecho_mascot_{expression}.svg"
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    return path


def get_all_expressions() -> dict[str, str]:
    """获取所有表情的 SVG"""
    return {expr: get_svg(expr) for expr in ["idle", "singing", "thinking", "happy", "surprised"]}


def get_html_widget(expression: str = "idle", size: int = 200) -> str:
    """生成可嵌入 HTML 的 widget 代码"""
    svg = get_svg(expression)
    return f"""<div class="mindecho-mascot {expression} pop-in" style="width:{size}px;height:{size}px;">
  <div class="mascot-speech-bubble">需要帮助吗？</div>
  {svg.replace('<svg ', f'<svg width="{size}" height="{size}" ')}
</div>"""
