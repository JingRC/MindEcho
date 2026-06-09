# MindEcho 练声模式 — 完整设计文档

> 版本：V1.0-draft  
> 日期：2026-06-08  
> 状态：设计评审中

---

## 目录

1. [概述与目标](#1-概述与目标)
2. [评价体系](#2-评价体系)
3. [伴奏模式](#3-伴奏模式)
4. [视觉交互设计](#4-视觉交互设计)
5. [练习库设计](#5-练习库设计)
6. [架构设计](#6-架构设计)
7. [分阶段实施计划](#7-分阶段实施计划)
8. [技术选型](#8-技术选型)

---

## 1. 概述与目标

### 1.1 是什么

练声模式是 MindEcho 的新增子模块，在现有的普通模式/低延模式之外，提供**交互式音准训练**功能：

- 系统预设目标音符序列（音阶/琶音/旋律片段）
- 钢琴合成伴奏/参考音
- 用户跟唱，实时检测音高
- **银色→金色**音高线视觉反馈
- 多维度评分 + 评价体系

### 1.2 核心原则

1. **实时优先**：练声对延迟敏感，优先走轻量管线（参考低延模式，可降级到普通模式）
2. **设备自适应**：根据设备采样率自动调整管线参数，不要求 192kHz 也能用
3. **渐进复杂度**：V1 从 C 大调单音开始，逐步扩展
4. **与现有系统融合**：复用 profile 存档、pitch_service、可视化引擎

---

## 2. 评价体系

### 2.1 容差等级

| 等级 | Cents 偏差 | 标签 | 线色 | 交互效果 |
|------|-----------|------|------|---------|
| **Perfect** | ±0～15 | `PERFECT!` | 亮金 + 光晕 | 音符旁闪烁"PERFECT"标签，粒子特效 |
| **Great** | ±16～25 | `GREAT` | 金色 | 音符变金，小闪光 |
| **Good** | ±26～35 | `Good` | 淡金 | 音符变淡金 |
| **OK** | ±36～50 | — | 银色微闪 | 线保持银色，微弱闪烁 |
| **Miss** | >±50 | `Miss` | 灰色 | 线变灰，无高亮 |

**研究依据**：
- 人耳 JND ≈ 25 cents（Pfordresher & Demorest, 2020）
- 专业歌手偏差 15–20 cents（Biswas et al., 2020）
- 未训练者偏差 50+ cents（同上）

### 2.2 评分维度（单个练习）

| 维度 | 权重 | 计算方法 | 说明 |
|------|------|---------|------|
| **音准 (Pitch Accuracy)** | 50% | Perfect=1.0, Great=0.85, Good=0.7, OK=0.4, Miss=0 的加权平均 | 核心维度 |
| **稳定性 (Stability)** | 20% | 1.0 - std_dev_cents/100，钳位到 [0,1] | 音高抖动越小分越高 |
| **节奏 (Timing)** | 15% | 每个音 onset 偏差 < 150ms 的比例 | 是否在节拍内起音 |
| **持续力 (Hold)** | 10% | 实际保持时长 / 目标时长的平均值 | 是否偷懒提前断音 |
| **音域适应 (Range Fit)** | 5% | 练习是否在用户已校准的音域内 | 鼓励在舒适音域练习 |

### 2.3 总评等级（练习结束后）

| 总分 | 等级 | 描述 |
|------|------|------|
| 95–100% | ⭐ S — 专业级 | "接近专业歌手水准，音准极其稳定" |
| 85–94% | A — 优秀 | "音准优秀，具备良好声乐基础" |
| 70–84% | B — 良好 | "音准良好，部分细节可再打磨" |
| 50–69% | C — 入门 | "有一定音感，建议加强音阶基础练习" |
| <50% | D — 待提高 | "别灰心！坚持每天练习 10 分钟，进步看得见" |

### 2.4 Profile 持久化存储

在 `SingerProfile` 中新增 `TrainingStats`：

```python
@dataclass
class TrainingStats:
    total_sessions: int = 0           # 练声总次数
    total_minutes: float = 0.0        # 练声总时长
    average_score: float = 0.0        # 平均总分
    pitch_accuracy_avg: float = 0.0   # 平均音准分
    stability_avg: float = 0.0        # 平均稳定分
    best_score: float = 0.0           # 历史最高分
    level: str = "beginner"           # beginner / intermediate / advanced / expert
    level_progress: float = 0.0       # 当前等级进度 0-1
    exercise_history: list = field(default_factory=list)  # [{exercise_id, score, date}, ...]
    vocal_range_low: float = 0.0      # 练声中测得的舒适低音
    vocal_range_high: float = 0.0     # 练声中测得的舒适高音
```

### 2.5 等级晋升机制

```
Beginner (入门)  →  平均分 > 70 且累计 20 次练习
Intermediate (中级) →  平均分 > 80 且累计 50 次练习
Advanced (高级) →  平均分 > 88 且累计 100 次练习
Expert (专家级) →  平均分 > 93 且累计 200 次练习
```

---

## 3. 伴奏模式

### 3.1 四种模式

| 模式 | 行为 | 适用场景 |
|------|------|---------|
| **先听后唱** (Listen & Repeat) | 弹参考音 → 停顿 → 用户跟唱 | 初学者建立音感 |
| **全程伴奏** (Continuous Accomp.) | 钢琴持续弹奏，用户对着唱 | 进阶者跟伴奏能力 |
| **静默模式** (Silent / Sight-sing) | 只给视觉提示，无音频 | 检验真正音准独立性 |
| **智能模式** (Smart，推荐默认) | 首次练习→先听后唱；重练→全程伴奏 | 循序渐进减少依赖 |

### 3.2 用户可选设置

```
练声伴奏设置 ⚙️
├─ 模式: 智能 / 先听后唱 / 全程 / 静默
├─ 伴奏音量: 0–100%
├─ 参考音时长: 0.5s / 1.0s / 1.5s
├─ 预备拍: 0拍 / 1拍 / 2拍
├─ 速度: ♩= 40–200
├─ 移调: ±12 半音
└─ 自动音域适配: 开 / 关
```

### 3.3 技术实现

MIDI 合成方案：**`mido` + `fluidsynth` (或 `pyfluidsynth`)**

```
MIDI 文件 (或程序生成 note_on/off) 
  → mido 解析/MIDI 消息生成
  → FluidSynth + SoundFont (.sf2) 渲染为 PCM
  → 混入回听/监听音频流
```

备选：预渲染 12 个大调 × 8 种练习类型 × 3 个八度 = 288 个 WAV 文件（体积 ~50MB），`pydub` + FFmpeg 直接播放。

---

## 4. 视觉交互设计

### 4.1 钢琴卷帘 / 目标音符区

```
时间轴 →
│
│  🎵 C5  ───[────────────]───      ← 目标音条（灰色=待命中）
│  🎵 B4  ──────[────────]─────
│  🎵 A4  ─────────[────────]──
│  🎵 G4  ────────────[─────]─
│  🎵 F4  ───────────────[──]─
│  🎵 E4  ─────────────────────
│  🎵 D4  ─────────[────────]──
│  🎵 C4  ───[────────────]───      ← 起始音
│
└──────────────────────────────────→
  播放头 ⬆ 向右扫描
```

### 4.2 音高线（ECG 曲线叠加）

- 线色跟随命中等级实时变化
- **灰色**：未开始 / Miss
- **银色**：OK（在容差边缘）
- **淡金**：Good
- **金色**：Great
- **亮金 + 粒子**：Perfect

### 4.3 命中时交互

```
  🎯 C5  ───[════════════]───  PERFECT! ✨
                    ↑
              金色 + 粒子特效 + "PERFECT" 标签弹出
```

- Perfect → 金色光晕扩散 + "PERFECT!" 标签淡入淡出
- Great → 金色闪光 + "GREAT" 标签
- Good → 音符区变淡金
- Miss → 音符区保持暗灰，无特效

---

## 5. 练习库设计

### 5.1 练习数据结构

```python
@dataclass
class VocalExercise:
    id: str                          # 如 "c_major_scale_ascending"
    name: str                        # "C大调上行音阶"
    description: str                 # 练习说明
    difficulty: int                  # 1-10
    category: str                    # scale / arpeggio / interval / melody / warmup
    key: str                         # "C" / "G" / "F" / ... / "chromatic"
    notes: List[TargetNote]          # 目标音符序列
    tempo: int                       # 默认 BPM
    accompaniment_midi: Optional[str]  # MIDI 数据或文件路径
    tags: List[str]                  # ["beginner", "warmup", "diatonic"]

@dataclass
class TargetNote:
    midi_note: int                   # MIDI 音符号 (60=C4)
    duration_beats: float            # 持续拍数
    label: str                       # "C4" / "Do" / "1"
    lyric: Optional[str]             # 可选用歌词/元音 ("ah", "ee", "la")
```

### 5.2 分阶段练习库

| 阶段 | 调性 | 练习类型 | 数量 |
|------|------|---------|------|
| **V1.0** | C 大调 | 单音匹配、五声音阶、大三和弦琶音、八度音阶 | ~12 个 |
| **V1.1** | C 大调 | 小三和弦、上下行交替、简单旋律片段 | ~10 个 |
| **V1.2** | G、F 大调 | 同上所有 | ~24 个 |
| **V1.3** | 全部大调 | 自动移调 | 全量 |
| **V2.0** | 大调+小调 | 半音阶、跳进、和声进行 | ~50 个 |

### 5.3 课程模式 vs 自由练习

| 维度 | 自由练习 | 课程模式 |
|------|---------|---------|
| 选曲 | 用户自己挑 | 系统按等级递进推荐 |
| 顺序 | 任意 | 锁定（通过前一个解锁后一个） |
| 难度 | 用户自选 | 自适应（根据历史成绩动态调整） |
| 反馈 | 即时得分 | 即时得分 + 累计进度条 + 等级晋升 |

---

## 6. 架构设计

### 6.1 模式层级

```
                    ┌─────────────────┐
                    │   MainWindow     │
                    │ (模式切换控制)    │
                    └──────┬──────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
   │  普通模式    │  │  低延模式    │  │ 练声模式 🆕 │
   │ matplotlib  │  │  pyqtgraph  │  │ pyqtgraph   │
   ├─────────────┤  ├─────────────┤  ├─────────────┤
   │ 降噪 ✅     │  │ 降噪 简化   │  │ 降噪 轻量   │
   │ VAD ✅      │  │ VAD 简化    │  │ VAD ❌      │
   │ 假声分类 ✅ │  │ 假声分类 ❌  │  │ 假声分类 ❌  │
   │ 换气检测 ✅ │  │ 换气检测 ❌  │  │ 换气检测 ❌  │
   │ 延迟 ~15ms  │  │ 延迟 ~6ms   │  │ 延迟 ~4ms   │
   └─────────────┘  └─────────────┘  └─────────────┘
         │                │                │
         └────────────────┴────────────────┘
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
     ┌──────────────┐      ┌──────────────────┐
     │ PitchService │      │ AudioRecorder     │
     │ (YIN 检测)   │      │ (InputStream)     │
     └──────────────┘      └──────────────────┘
                                     │
                          ┌──────────┴──────────┐
                          ▼                     ▼
                  ┌──────────────┐    ┌──────────────────┐
                  │ 练声评分引擎  │    │ MIDI 伴奏引擎     │
                  │ (Pitch→Score)│    │ (mido+fluidsynth) │
                  └──────────────┘    └──────────────────┘
```

### 6.2 新增文件

```
src/
├── vocal_training/
│   ├── __init__.py
│   ├── training_engine.py        # 练声核心引擎（状态管理、评分）
│   ├── exercise_library.py       # 练习库定义与加载
│   ├── scoring.py                # 评分与评价体系
│   ├── accompaniment.py          # MIDI 伴奏引擎
│   ├── training_visualizer.py    # 练声专用可视化（钢琴卷帘+ECG）
│   └── training_ui.py            # 练声 UI 面板（控件、设置）
├── gui/
│   └── integrated_recording_interface.py  # 新增练声 Tab + 模式切换
├── profiles/
│   └── profile_model.py          # 新增 TrainingStats
```

### 6.3 管线对比

| 组件 | 普通模式 | 练声模式 |
|------|---------|---------|
| 降噪 | 基础频域降噪 | 仅 notch filter (50/60Hz) |
| VAD/门控 | 完整迟滞门控 (hysteresis) | ❌ 跳过 |
| 假声分类 | SqueezeNet 推理 | ❌ 跳过 |
| 换气检测 | 多规则联合 | ❌ 跳过 |
| 声部分离 | LFM 模式 | ❌ 跳过 |
| 音高检测 | YIN (与服务相同) | YIN (精简参数) |
| 后处理 | EMA + 跳变抑制 | 轻量 EMA (alpha=0.85) |
| 节流发射 | 12ms 批处理 | 4ms 直发 |
| 可视化 | ECG + 五线谱 | 钢琴卷帘 + 目标音 + ECG 叠加 |

---

## 7. 分阶段实施计划

### Phase 1: 核心引擎 (预计 3-4 轮对话)

- [ ] `training_engine.py` — 练声状态机 (idle → listening → singing → scoring)
- [ ] `scoring.py` — 五级评价体系 (Perfect/Great/Good/OK/Miss)
- [ ] `exercise_library.py` — C 大调练习定义（~12 个）
- [ ] 练声模式音频管线（轻量版，复用 `pitch_service`）

### Phase 2: 可视化 (预计 2-3 轮)

- [ ] `training_visualizer.py` — 钢琴卷帘 + 目标音符条
- [ ] 银色→金色渐变音高线
- [ ] 命中特效（标签弹出、光晕）
- [ ] 实时评分面板

### Phase 3: 伴奏引擎 (预计 2-3 轮)

- [ ] `accompaniment.py` — MIDI 合成 + SoundFont
- [ ] 四种伴奏模式实现
- [ ] 伴奏与音频流混音

### Phase 4: UI 集成 (预计 2-3 轮)

- [ ] 主窗口新增"练声模式" Tab
- [ ] 模式切换（普通 ↔ 练声，共享音频流）
- [ ] 伴奏设置面板
- [ ] 练习浏览器 + 课程/自由模式切换

### Phase 5: 评价系统对接 (预计 1-2 轮)

- [ ] Profile 对接 — TrainingStats 存储
- [ ] 历史练习记录
- [ ] 等级晋升逻辑
- [ ] 进步曲线可视化

### Phase 6: 扩展 (后续版本)

- [ ] 移调支持（全大调）
- [ ] 音域自动检测
- [ ] 课程模式（自适应推荐）
- [ ] 小调、半音阶等高级练习

---

## 8. 技术选型

| 需求 | 选择 | 备选 | 理由 |
|------|------|------|------|
| MIDI 合成 | `mido` + `pyfluidsynth` | `pygame.midi` | mido 纯 Python、跨平台；fluidsynth 音质好 |
| SoundFont | `FluidR3_GM.sf2` (141MB) | 轻量 `TimGM6mb.sf2` (5.7MB) | 先用轻量版，后续可替换 |
| 音频混音 | NumPy 直接叠加 | `pydub` | 低延迟，无需额外依赖 |
| 可视化 | **pyqtgraph** (参考低延模式) | matplotlib | 性能优、支持高频更新、已有 PyQtGraphPitchRenderer |
| 音频流 | 复用 `sounddevice.InputStream` | — | 与现有架构一致 |
| 延迟优化 | 设备自适应采样率 + 块大小 | — | 复用现有 config 探测体系 |

---

## 附录 A: 评价标签总览

| 标签 | 触发条件 | 视觉效果 |
|------|---------|---------|
| `PERFECT!` | ±0～15 cents | 亮金 + 光晕粒子 |
| `GREAT` | ±16～25 cents | 金色闪光 |
| `Good` | ±26～35 cents | 淡金高亮 |
| `Early` | onset > 150ms 提前 | 黄色提示 |
| `Late` | onset > 150ms 延后 | 黄色提示 |
| `Hold` | 持续力 > 90% | 绿色 `+HOLD` 徽章 |
| `Miss` | > ±50 cents | 灰色暗沉 |
| `Streak!` | 连续 5+ 个 Perfect/Great | 连击计数弹出 |

## 附录 B: 与现有系统的交互点

| 系统 | 交互方式 |
|------|---------|
| `PitchDetectionService` | 练声模式复用，关闭额外后处理 |
| `SingerProfile` / `ProfileManager` | 新增 `TrainingStats` 字段 |
| `AudioRecorder` | 共享 `InputStream`，练声模式可选监听混音 |
| `ECGStylePitchVisualizer` | 不直接使用；新建 `TrainingVisualizer` |
| `IntegratedRecordingInterface` | 新增 `show_training_mode()` / Tab 切换 |
| `PerformanceManager` | 练声模式新增 `TRAINING` 性能档位 |
| `_apply_actual_input_samplerate` | 复用，设备自适应 |
