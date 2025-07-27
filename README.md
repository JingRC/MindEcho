# MindEcho - 智能音频录制与分析系统

## 🎵 项目简介

MindEcho 是一个集成了实时音高检测和五线谱可视化的智能音频录制系统。系统支持多种GUI框架，提供从基础录音到高级音乐分析的完整功能。

## ⭐ 核心功能

### �️ 录音功能
- 多格式录音支持 (WAV, MP3)
- 可调采样率和通道数
- 实时录音监控
- 文件自动管理

### 🎯 音高检测
- **YIN算法** - 高精度音高检测
- **自相关法** - 经典频率分析
- **FFT分析** - 频谱基音检测
- 实时音符识别
- 音准偏差计算 (cents)

### � 五线谱可视化
- 实时五线谱显示
- 音符自动定位
- 音高曲线绘制
- 升降号支持
- 多八度显示

### 🚀 多模式启动
- **增强版** - 完整功能 (音高检测 + 可视化)
- **标准版** - 基础录音 (PyQt界面)
- **简化版** - 轻量级 (tkinter界面)

## 📋 系统要求

### Python版本
- Python 3.7+

### 核心依赖
```bash
numpy          # 数值计算
scipy          # 信号处理  
sounddevice    # 音频录制
matplotlib     # 图形绘制
```

### GUI框架 (任选其一)
```bash
PyQt6          # 推荐 - 现代界面
PyQt5          # 兼容 - 稳定支持
tkinter        # 内置 - 基础界面
```

## �️ 安装指南

### 1. 克隆项目
```bash
git clone <repository-url>
cd MindEcho
```

### 2. 安装依赖
```bash
# 基础依赖
pip install numpy scipy sounddevice matplotlib

# GUI框架 (选择一个)
pip install PyQt6          # 推荐
# 或
pip install PyQt5          # 兼容
# tkinter 通常已预装
```

### 3. 启动应用
```bash
# 使用增强版启动器
python run_enhanced.py

# 或使用原版启动器
python run_mindecho.py
```

## 🎮 使用指南

### 启动模式选择

#### 1. 🚀 增强版模式
```bash
python run_enhanced.py
选择: 1. 增强版
```
- 完整的音高检测功能
- 实时五线谱可视化
- 音符识别和显示
- 音高曲线分析

#### 2. 📱 标准版模式
```bash
python run_enhanced.py
选择: 2. 标准版
```
- 基础录音功能
- 文件格式选择
- 播放和管理

#### 3. 🔧 简化版模式
```bash
python run_enhanced.py
选择: 3. 简化版
```
- 轻量级录音
- 简洁界面

### 音高检测使用

1. **开始音高分析**
   - 在增强版中点击"开始音高分析"
   - 系统将实时检测麦克风输入的音高

2. **查看实时信息**
   - 当前频率显示
   - 音符名称 (如 A4, C#5)
   - 音准偏差 (cents)

3. **五线谱可视化**
   - 实时显示检测到的音符
   - 音高曲线绘制
   - 历史音符显示

### 录音功能使用

1. **设置录音参数**
   - 采样率: 44100Hz (标准) / 48000Hz / 96000Hz
   - 声道: 单声道/立体声

2. **开始录音**
   - 点击"开始录音"按钮
   - 录音文件自动保存到 `recordings/` 目录

3. **文件管理**
   - 点击"打开录音文件夹"查看文件
   - 支持WAV格式录音

## 🔧 功能测试

### 运行测试工具
```bash
python test_mindecho.py
```

测试项目包括:
- ✅ 录音功能测试
- ✅ 音高检测算法测试
- ✅ 五线谱渲染测试
- ✅ GUI组件测试
- ✅ 综合功能测试

## 📁 项目结构

```
MindEcho/
├── src/
│   ├── audio_processing/
│   │   └── recorder.py          # 录音核心模块
│   ├── analysis/
│   │   ├── pitch_detection.py   # 音高检测算法
│   │   ├── realtime_analyzer.py # 实时分析器
│   │   └── staff_visualizer.py  # 五线谱可视化
│   └── gui/
│       ├── enhanced_main_window.py  # 增强版GUI
│       ├── pyqt6_main_window.py     # 标准版GUI
│       └── simple_gui.py            # 简化版GUI
├── recordings/              # 录音文件目录
├── run_enhanced.py         # 增强版启动器
├── run_mindecho.py         # 原版启动器
├── test_mindecho.py        # 功能测试工具
└── README.md
```

## 🎼 音乐理论支持

### 音高检测算法

1. **YIN算法**
   - 基于AMDF (Average Magnitude Difference Function)
   - 高精度基音检测
   - 适合人声和乐器

2. **自相关法**
   - 经典时域分析方法
   - 计算信号的周期性
   - 稳定可靠

3. **FFT分析**
   - 频域分析方法
   - 基于谱峰检测
   - 快速计算

### 音符系统
- 12平均律音高系统
- MIDI音符编号对应
- 音名表示 (C, D, E, F, G, A, B)
- 升降号支持 (#, b)
- 八度标记 (C4 = 中央C)

### 五线谱显示
- 高音谱号显示
- 标准五线谱布局
- 加线音符支持
- 实时音符定位

## 🔍 故障排除

### 常见问题

1. **无法启动GUI**
   ```bash
   # 安装GUI框架
   pip install PyQt6
   # 或
   pip install PyQt5
   ```

2. **音频设备错误**
   - 检查麦克风权限
   - 确认音频设备连接
   - 尝试不同的音频设备

3. **依赖包缺失**
   ```bash
   # 自动安装
   python run_enhanced.py
   # 选择自动安装选项
   ```

4. **音高检测不准确**
   - 确保环境安静
   - 调整音量大小
   - 尝试不同的检测算法

### 性能优化

1. **降低延迟**
   - 减小chunk_size
   - 使用较低采样率

2. **提高精度**
   - 增加chunk_size
   - 使用YIN算法
   - 环境降噪

## 🤝 开发贡献

### 代码结构
- 模块化设计
- 清晰的接口定义
- 完整的错误处理
- 详细的文档注释

### 扩展功能
- 可以添加更多音高检测算法
- 扩展可视化效果
- 支持更多音频格式
- 添加音乐理论分析

## 🎉 致谢

感谢所有为开源音频处理和音乐理论做出贡献的开发者们！

---

**享受使用 MindEcho 进行音频录制和音乐分析吧！** 🎵
- **Python版本**: 3.7 或更高
- **音频设备**: 支持音频输入的设备（麦克风、声卡等）

### 必需依赖
- `sounddevice`: 音频录制和播放
- `numpy`: 数值计算
- `scipy`: 科学计算（音频文件I/O）

### 可选依赖
- `PyQt5`: 现代化GUI界面（推荐）
- `pandas`: 数据处理和分析
- `matplotlib`: 图表和可视化

## 项目结构

```
MindEcho/
├── src/                          # 源代码目录
│   ├── audio_processing/         # 音频处理模块
│   │   └── recorder.py          # 核心录音器类
│   ├── gui/                      # 图形界面模块
│   │   ├── main_window.py       # PyQt5主界面
│   │   └── simple_gui.py        # tkinter简化界面
│   ├── analysis/                 # 音频分析模块（预留）
│   ├── data/                     # 数据存储
│   └── utils/                    # 工具函数
├── recordings/                   # 默认录音保存目录
├── docs/                         # 文档
├── tests/                        # 测试文件
├── requirements.txt              # Python依赖列表
├── install_dependencies.bat      # Windows安装脚本
└── run_mindecho.py              # 主启动脚本
```

## 使用说明

### 录音操作

1. **启动应用**: 运行 `python run_mindecho.py`
2. **查询设备**: 点击"查询设备"按钮查看可用的音频输入设备
3. **设置参数**: 根据需要调整采样率、声道数等参数
4. **开始录音**: 点击"开始录音"按钮
5. **停止录音**: 点击"停止录音"按钮自动保存文件
6. **查看文件**: 点击"打开文件夹"查看保存的录音文件

### 参数建议

| 用途 | 采样率 | 声道 | 数据类型 | 说明 |
|------|--------|------|----------|------|
| 语音录制 | 16000 Hz | 单声道 | int16 | 适合语音识别和处理 |
| 音乐录制 | 44100 Hz | 立体声 | int16 | CD质量，适合音乐 |
| 高精度分析 | 48000 Hz | 单声道 | float32 | 专业音频分析 |

### 录音文件命名

录音文件自动按时间戳命名，格式为：
- `recording_YYYYMMDD_HHMMSS.wav`
- 例如：`recording_20250121_143052.wav`

## 故障排除

### 常见问题

1. **"无法启动录音"错误**:
   - 检查麦克风是否连接并启用
   - 确认应用有麦克风使用权限
   - 尝试查询设备确认音频设备状态

2. **"模块导入失败"错误**:
   - 运行 `install_dependencies.bat` 安装依赖
   - 手动安装: `pip install sounddevice numpy scipy`

3. **GUI启动失败**:
   - 系统会自动降级到tkinter版本
   - 如需PyQt5版本，手动安装: `pip install PyQt5`

4. **录音质量问题**:
   - 调整采样率和数据类型设置
   - 检查麦克风距离和环境噪音
   - 尝试不同的音频设备

### 性能优化

- **内存使用**: 长时间录音可能消耗较多内存
- **CPU使用**: 高采样率会增加CPU负担
- **存储空间**: 44100Hz立体声每分钟约10MB

## 开发信息

### 核心技术

- **音频处理**: sounddevice + numpy
- **GUI框架**: PyQt5 (主要) + tkinter (备选)
- **文件格式**: WAV (scipy.io.wavfile)
- **多线程**: 非阻塞录音和UI响应

### 扩展计划

- [ ] 音频可视化（波形图、频谱图）
- [ ] 实时音频分析
- [ ] 音频格式转换
- [ ] 云端集成
- [ ] 语音识别集成

## 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## 贡献

欢迎提交问题报告、功能请求和代码贡献！

---

**MindEcho Team** - 让录音更智能，让分析更简单