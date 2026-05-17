"""System prompt 模板 —— 为不同场景提供专门的 Agent 提示词

支持双重身份：日常陪伴的朋友 + 专业声乐教练，根据话题自然切换。
"""

from __future__ import annotations

from ..identity import CoachIdentity


# ═══════════════════════════════════════════════════════════════
# 核心 System Prompt（双重身份：朋友 + 声乐教练）
# ═══════════════════════════════════════════════════════════════

_SYSTEM_PROMPT_TEMPLATE = """你是{name}，一个{personality}、懂音乐的伙伴。你可以闲聊也可以教唱歌，根据对方在聊什么自然地切换状态。

你的说话方式：
- 像朋友聊天一样自然，有自己的小性格和小情绪。不要像客服机器人，不要列 bullet points，不要"首先其次最后"
- 日常聊天时：轻松、随意、偶尔开个小玩笑。比如聊聊今天的心情、喜欢的歌、最近在听什么。像一个也热爱音乐的好朋友
- 对方问唱歌相关的问题时：你可以切换到认真的语气，用你的声乐知识帮 ta 分析、给建议。从呼吸、发声、共鸣到各种技巧你都很熟（EVT、CVT、Bel Canto、CCM 这些体系你都了解），流行 R&B 摇滚爵士音乐剧古典也都行
- 给专业建议时要具体到细节，不要空泛。"加强气息"这种话太水了，要说"你第二段副歌那个'梦'字一上去气息就松了，试试在前面抢一口气顶住"
- 如果有 MindEcho 的演唱数据，用具体数字说话："这句平均偏低了 20 音分，比上周好一些了"
- 鼓励但要真诚，别尬夸。用户唱得有问题就直接说，但要带着"我帮你一起搞定"的态度
- 声带不舒服、嗓子疼这类情况，第一反应永远是让 ta 休息、必要时看医生，别硬练
- 一次别给太多建议，聚焦最重要的 1-2 个点。说太多等于没说
- 始终用中文

{{memory}}"""


def build_system_prompt(identity: CoachIdentity, memory_text: str = "",
                        coaching_mode: bool = False, knowledge_text: str = "") -> str:
    """根据教练身份和上下文动态构建 system prompt。

    Args:
        identity: 教练身份配置（名称、性格等）
        memory_text: 格式化的记忆上下文文本
        coaching_mode: 是否为专业指导模式（注入知识库内容）
        knowledge_text: 声乐知识库检索结果（仅 coaching_mode 时使用）
    """
    prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        name=identity.name,
        personality=identity.personality,
    )
    if memory_text:
        prompt = prompt.replace("{memory}", f"\n## 关于用户的记忆\n{memory_text}")
    else:
        prompt = prompt.replace("{memory}", "")

    if coaching_mode and knowledge_text:
        prompt += f"\n\n## 声乐知识库参考\n以下是知识库中与用户问题相关的专业内容，请参考这些内容给出专业指导：\n\n{knowledge_text}"

    return prompt


# 向后兼容：旧的静态 SYSTEM_PROMPT
SYSTEM_PROMPT = _SYSTEM_PROMPT_TEMPLATE.format(
    name="小艾",
    personality="温暖鼓励",
).replace("{memory}", "")


# ═══════════════════════════════════════════════════════════════
# 意图检测 —— 判断用户是在闲聊还是请教声乐问题
# ═══════════════════════════════════════════════════════════════

# 声乐教练相关关键词（命中任一即判定为 coaching intent）
_COACHING_KEYWORDS = [
    # 歌唱技术
    "唱歌", "唱", "唱法", "高音", "低音", "中音", "音域", "音准", "跑调", "破音", "走音",
    "发抖", "发紧", "发虚", "不稳", "声音抖", "嗓子紧",
    "气息", "呼吸", "丹田", "腹式呼吸", "换气", "憋气",
    "共鸣", "头腔", "胸腔", "鼻腔", "面罩",
    "混声", "胸声", "头声", "假声", "真声", "咽音", "强混", "弱混", "平衡混",
    "声区", "换声", "换声点", "过桥", "passaggio",
    "颤音", "直音", "滑音", "转音", "哨音", "海豚音", "气泡音", "怒音", "嘶吼",
    "咬字", "吐字", "元音", "辅音", "归韵",
    "声带", "喉咙", "嗓子", "喉位", "喉头",
    "副歌", "主歌", "bridge", "间奏", "尾奏",
    "闭合", "挡气", "支撑", "belting", "twang", "sob", "SOVT",
    # 练习
    "练声", "练习", "训练", "开嗓", "吊嗓子", "基本功",
    "音阶", "爬音", "琶音", "哼鸣", "唇颤", "打嘟", "弹唇",
    "练歌", "歌曲", "曲目", "演唱", "翻唱", "表演", "舞台",
    # 分析
    "分析", "评估", "诊断", "反馈", "测评", "测试",
    "音分", "偏差", "节奏", "拍子", "拖拍", "抢拍",
    # 课程
    "课程", "学唱歌", "教学", "教程", "方法", "技巧",
    "改善", "提升", "进阶", "突破", "瓶颈",
    # 风格
    "流行", "美声", "民族", "音乐剧", "摇滚", "爵士", "R&B", "说唱",
    "通俗", "戏曲", "民谣", "古典", "歌剧",
    # 声带健康
    "护嗓", "养嗓", "禁声", "嘶哑", "疲劳", "用声过度",
]

# 明确的日常闲聊关键词（用于降低误判）
_CASUAL_KEYWORDS = [
    "你好", "嗨", "哈喽", "hello", "hi", "hey",
    "早安", "晚安", "早上好", "晚上好", "下午好",
    "天气", "今天", "吃了", "在干嘛", "在吗", "在不",
    "讲个笑话", "聊聊天", "聊天", "闲聊",
    "叫什么", "你是谁", "怎么样", "推荐", "喜欢",
]


def detect_intent(user_message: str) -> tuple[bool, float]:
    """检测用户意图：是声乐请教还是日常闲聊。

    基于关键词匹配（轻量级，不消耗额外 LLM 调用）。

    Returns:
        (is_coaching, confidence): is_coaching 为 True 表示声乐请教；
        confidence 为 0.0-1.0 的置信度。
    """
    msg_lower = user_message.lower().strip()

    coaching_hits = sum(1 for kw in _COACHING_KEYWORDS if kw in msg_lower)
    casual_hits = sum(1 for kw in _CASUAL_KEYWORDS if kw in msg_lower)

    if coaching_hits == 0 and casual_hits == 0:
        # 无法判断 → 默认为闲聊，保持轻松语气
        return False, 0.3

    if coaching_hits > 0 and casual_hits == 0:
        confidence = min(0.95, 0.6 + coaching_hits * 0.15)
        return True, confidence

    if casual_hits > 0 and coaching_hits == 0:
        confidence = min(0.95, 0.6 + casual_hits * 0.15)
        return False, confidence

    # 两者都有 → 看哪边更多
    if coaching_hits >= casual_hits:
        return True, 0.55
    else:
        return False, 0.55


# ═══════════════════════════════════════════════════════════════
# 联网搜索意图检测
# ═══════════════════════════════════════════════════════════════

_SEARCH_KEYWORDS = [
    # 推荐类
    "推荐", "推荐歌", "推荐几首", "有什么好听的", "有什么歌", "哪些歌",
    "推荐歌手", "推荐专辑", "安利", "种草",
    # 时效类
    "最新", "最近", "新歌", "新专辑", "新出", "刚出", "近期",
    "最近在流行", "现在流行", "今年", "这个月",
    # 信息查询
    "是谁", "什么是", "介绍一下", "介绍下", "科普",
    "有哪些", "哪个", "哪首", "什么风格", "什么类型",
    "代表作", "专辑", "演唱会", "巡演",
    # 搜索
    "搜索", "查一下", "帮我找", "帮我查", "搜一下", "找一下",
    "帮我搜",
    # 新闻动态
    "新闻", "动态", "八卦", "最新消息", "热点",
    # 排行榜
    "排行榜", "榜单", "排名", "热门", "TOP", "top",
    # 歌词
    "歌词", "lyrics",
]


def detect_search_intent(user_message: str) -> bool:
    """检测用户是否在问需要联网搜索才能回答的问题。

    推荐歌曲、最新动态、事实查询等触发搜索，
    声乐技术、个人话题等不触发（由知识库和 LLM 自身知识覆盖）。
    """
    msg_lower = user_message.lower().strip()
    return any(kw in msg_lower for kw in _SEARCH_KEYWORDS)


# ═══════════════════════════════════════════════════════════════
# 场景专用提示词片段
# ═══════════════════════════════════════════════════════════════

ANALYSIS_PROMPT = """
## 当前任务：演唱分析
用户刚完成了一次演唱，MindEcho 已生成了详细的音高分析数据。
请根据以下上下文数据，为用户提供分析反馈：

{singing_context}

请按以下结构回复：
1. **整体评估** (1-2句)：本次演唱的总体水平评价
2. **音准分析**：指出音准最好和最差的部分，分析偏差模式（偏高/偏低）
3. **技巧点评**：对颤音、滑音、声区切换等技巧使用进行评价
4. **改进建议** (最重要的部分)：给出 1-2 个具体、可操作的改进建议，包含练习方法
5. **鼓励与下一步**：肯定进步，推荐下一步的练习方向
"""

COMPARISON_PROMPT = """
## 当前任务：对比分析
用户演唱了 {song_name}，并与专业歌手 {reference_singer} 的版本进行了对比。

{singing_context}

请按以下结构回复：
1. **总体差距**：综合评估和专业歌手的差距（用数据说明）
2. **逐段对比**：每个段落（主歌/副歌等）的具体差异
3. **技巧差距**：专业歌手在哪些位置使用了什么技巧？用户是否尝试了类似的处理？
4. **模仿建议**：为了让用户的演唱更接近专业版本，建议从哪些方面入手？
5. **个人特色**：提醒用户可以保留的个人特色（不必完全复制）
"""

QA_PROMPT = """
{singing_context}
（按你的判断自然地回应就好，别刻意。）"""

COACHING_QA_PROMPT = """
用户想聊唱歌相关的话题。用你的专业知识认真帮 ta 分析，给具体能落地的那种建议。别灌水。

{singing_context}"""

PRACTICE_PLAN_PROMPT = """
## 当前任务：制定练习计划
请根据用户的当前水平和学习目标，制定一个符合 MindEcho 课程大纲的练习计划。

{curriculum_context}

{singing_context}

用户目标: {user_goal}

请回复：
1. **当前阶段评估**：用户在课程大纲中的位置
2. **本周重点** (1-2 个核心目标)
3. **每日练习计划** (简洁的 5 天计划)
4. **检查标准**：本周结束时应该达到什么效果
5. **进阶方向**：达到本周目标后的下一步
"""


# ═══════════════════════════════════════════════════════════════
# Prompt 组装工具
# ═══════════════════════════════════════════════════════════════


def build_analysis_prompt(singing_context: str) -> str:
    return ANALYSIS_PROMPT.format(singing_context=singing_context)


def build_comparison_prompt(
    singing_context: str,
    song_name: str = "未知歌曲",
    reference_singer: str = "专业歌手",
) -> str:
    return COMPARISON_PROMPT.format(
        singing_context=singing_context,
        song_name=song_name,
        reference_singer=reference_singer,
    )


def build_qa_prompt(
    singing_context: str = "",
    coaching_mode: bool = False,
) -> str:
    if coaching_mode:
        return COACHING_QA_PROMPT.format(
            singing_context=singing_context or "（暂无演唱数据）",
        )
    return QA_PROMPT.format(
        singing_context=singing_context or "（暂无演唱数据）",
    )


def build_practice_plan_prompt(
    curriculum_context: str = "",
    singing_context: str = "",
    user_goal: str = "全面提升歌唱能力",
) -> str:
    return PRACTICE_PLAN_PROMPT.format(
        curriculum_context=curriculum_context or "（课程大纲未加载）",
        singing_context=singing_context or "（暂无演唱数据）",
        user_goal=user_goal,
    )
