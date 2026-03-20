# 主唱/伴唱分离任务清单（执行版）

基线方案：docs/LEAD_BACKING_SEPARATION_EXECUTION_PLAN.md

使用规则：

- 每次开发前先更新“状态”和“当前负责人/日期”。
- 仅在对应验收标准通过后，将任务改为 done。
- 新需求先追加到“Backlog”，不要直接改动已完成项描述。

状态说明：

- todo：未开始
- doing：进行中
- blocked：被阻塞
- review：已完成待验证
- done：已验收完成

---

## A. 里程碑与总顺序

1. M1 架构与离线打通
2. M2 近实时链路打通
3. M3 质量优化与稳定性
4. M4 发布准备与回归

建议执行顺序：A01 -> A02 -> A03 -> B01 -> B02 -> B03 -> C01 -> C02 -> C03 -> D01 -> D02

---

## B. 执行任务清单

| ID  | 任务                                              | 优先级 | 依赖         | 状态   | 验收标准                                         |
| --- | ------------------------------------------------- | ------ | ------------ | ------ | ------------------------------------------------ |
| A01 | 建立 stage2 可插拔总管线（lead_backing_pipeline） | P0     | 无           | done   | 能在不影响现有人声/伴奏流程下，开关式启停 stage2 |
| A02 | 新增人声内部分离模块（vocal_internal_separator）  | P0     | A01          | review | 输入 vocal stem，输出 >=2 条候选人声轨           |
| A03 | 新增主唱归属模块（singer_embedding）              | P0     | A02          | review | 支持模板锁定与无模板自动归属两种路径             |
| B01 | 新增“主唱/伴唱设置窗口”并接入纯人声入口           | P0     | A01          | done   | 可配置：是否含伴唱、伴唱人数、识别方式、质量模式 |
| B02 | 新增预览试听（主唱独听/伴唱独听/混听 A/B）        | P0     | A02,A03,B01  | review | 用户可在确认前试听并切换轨道                     |
| B03 | 一次性绘制接入多轨结果（主唱优先视图）            | P0     | B02          | review | 离线绘制可切换：主唱-only / 主唱+伴唱            |
| C01 | 近实时分块调度（chunk/hop/overlap）               | P1     | A01,A02,A03  | doing  | 首帧延迟与稳态更新达到预算目标                   |
| C02 | 实时绘制轨道选择器与开关联动                      | P1     | C01,B01      | review | 实时可切换轨道显示，不卡 UI 主线程               |
| C03 | CPU/GPU 自动降级与性能保护策略                    | P1     | C01          | todo   | CPU 低算力时自动降级仍可用，无崩溃               |
| D01 | 指标埋点（碎点率/连续率/P95时延）                 | P1     | B03,C02      | todo   | 每次运行可生成可比较指标                         |
| D02 | 回归样本集与自动回归脚本                          | P1     | D01          | todo   | 20-50 首样本可一键回归并输出报告                 |
| D03 | 发布开关与回滚策略（feature flags）               | P0     | 全部核心任务 | todo   | 可一键回退到“仅人声/伴奏分离”                    |

---

## C. 子任务明细（按模块）

### C1. 代码结构任务

- [x] 新建 src/audio_processing/lead_backing/lead_backing_pipeline.py
- [x] 新建 src/audio_processing/lead_backing/vocal_internal_separator.py
- [x] 新建 src/audio_processing/lead_backing/singer_embedding.py
- [x] 新建 src/audio_processing/lead_backing/realtime_chunk_scheduler.py
- [x] 新建 src/audio_processing/lead_backing/quality_metrics.py

### C2. GUI 接入任务

- [x] 在纯人声模式入口新增“主唱/伴唱设置”按钮与参数状态显示
- [x] 在一次性绘制流程插入“分离 + 试听 + 确认”（已接入，待实机验证）
- [x] 在实时流程插入“近实时分离 + 轨道切换”（C02 第一版已接入，待实机验证）

### C3. 配置与开关任务

- [ ] 新增配置结构 lead_backing_config
- [ ] 新增 feature flags：
  - [ ] enable_lead_backing_stage2
  - [ ] enable_lead_template_lock
  - [ ] enable_realtime_lead_backing
- [ ] 新增参数落盘与恢复（QSettings）

### C4. 依赖与环境任务

- [x] 新增 requirements-optional.txt（不污染主依赖）
- [ ] 记录 CUDA/CPU 对应安装说明
- [ ] 启动前依赖自检（缺依赖时明确提示）

---

## D. 验收清单（必须逐项打勾）

### D1. 功能验收

- [ ] 可完成主唱/伴唱分离并可试听预览
- [ ] 可指定伴唱人数（0-4）且结果可见
- [ ] 主唱模板锁定可用
- [ ] 无模板自动归属可用

### D2. 质量验收

- [ ] 主唱碎点率较当前版本下降 >= 30%
- [ ] 嘈杂伴唱场景主唱连续率提升 >= 20%
- [ ] 伴唱误吸附率可被量化并低于内部阈值

### D3. 性能验收

- [ ] GPU：首次可视化延迟 <= 1.2s
- [ ] GPU：稳态 P95 <= 140ms
- [ ] CPU：首次可视化延迟 <= 2.0s
- [ ] CPU：稳态 P95 <= 260ms

### D4. 稳定性验收

- [ ] 异常输入（坏音频/空轨）不崩溃
- [ ] 缺模型/缺依赖时可回退且提示清晰
- [ ] feature flag 回滚路径可验证

---

## E. 本周冲刺模板（滚动更新）

### Sprint 当前目标

- 目标：M1 架构与离线打通
- 时间：2026-03-19
- Owner：Copilot + User

### Sprint 任务

- [x] A01
- [ ] A02（启发式基线已接入，待实机验证）
- [ ] A03（启发式归属已接入，待实机验证）
- [x] B01
- [ ] B02（功能已接入，待实机验证）
- [ ] B03（多轨切换已接入，待实机验证）
- [ ] C01（分块调度基础实现已接入，待接入实时链路）
- [ ] C02（实时轨道切换已接入，待第二轮实机验证）

### Sprint 风险

- 风险：
- 应对：

### Sprint 结果

- 完成：
- 未完成：
- 原因：
- 下周计划：

---

## F. Backlog（需求池）

- [ ] 自动建议伴唱人数（并允许手动覆盖）
- [ ] 伴唱轨自动命名与颜色风格预设
- [ ] 多语言 UI 文案与帮助提示
- [ ] 模型缓存可视化与清理入口

---

## G. 变更日志（每次改完必填）

- 日期：2026-03-19
- 修改人：Copilot
- 变更任务 ID：B03
- 变更文件：src/gui/integrated_recording_interface.py
- 指标变化：静态检查通过（No errors found），实机指标待补充
- 结论：一次性绘制已支持主唱-only / 主唱+伴唱模式切换，进入 review

- 日期：2026-03-19
- 修改人：Copilot
- 变更任务 ID：C01
- 变更文件：src/audio_processing/lead_backing/realtime_chunk_scheduler.py, src/audio_processing/lead_backing/lead_backing_pipeline.py, docs/LEAD_BACKING_MANUAL_TEST.md
- 指标变化：新增 chunk/hop/overlap 计算与首帧时延估算；实机时延待采样
- 结论：C01 从占位升级为可用基础实现，已可启动第一轮离线实测

- 日期：2026-03-19
- 修改人：Copilot
- 变更任务 ID：C02
- 变更文件：src/gui/integrated_recording_interface.py, docs/LEAD_BACKING_MANUAL_TEST.md
- 指标变化：新增实时轨道模式切换与开关联动；静态检查通过（No errors found）
- 结论：C02 第一版已接入，已开放第二轮实时实测入口

- 日期：2026-03-19
- 修改人：Copilot
- 变更任务 ID：C02
- 变更文件：src/gui/integrated_recording_interface.py
- 指标变化：新增本地实时“副轨同屏叠加（第一版）”，支持主唱/伴唱对照可视化；静态检查通过（No errors found）
- 结论：实时链路已支持单轨主分析 + 对照轨叠加显示，待实机确认观感与性能

- 日期：2026-03-19
- 修改人：Copilot
- 变更任务 ID：C02
- 变更文件：src/gui/integrated_recording_interface.py
- 指标变化：新增副轨颜色/透明度可配、实时面板叠加开关、仅播放时叠加与步进降采样（高质量/平衡/省电）
- 结论：C02 同屏叠加已具备可控观感与基础性能保护

- 日期：2026-03-19
- 修改人：Copilot
- 变更任务 ID：C02
- 变更文件：src/gui/integrated_recording_interface.py
- 指标变化：新增副轨独立图例/标签（画布右上角与实时面板来源提示）；叠加颜色/透明度/性能参数写入 QSettings 持久化
- 结论：C02 同屏叠加具备可识别标注与跨会话参数记忆能力

- 日期：2026-03-19
- 修改人：Copilot
- 变更任务 ID：C02
- 变更文件：src/gui/integrated_recording_interface.py
- 指标变化：新增图例位置（四角）/字号可配、短名映射（混合/主唱/伴唱）与“恢复默认”；新参数持久化到 QSettings
- 结论：C02 同屏叠加交互完成度进一步提升，可按偏好快速调参并保持跨会话一致

- 日期：2026-03-19
- 修改人：Copilot
- 变更任务 ID：C02
- 变更文件：src/gui/integrated_recording_interface.py
- 指标变化：新增“叠加诊断”状态区（副轨源、触发门控、当前点数、图例条件/可见性、叠加包计数）并 250ms 自动刷新
- 结论：可快速定位“看不到副轨/图例”的具体阻断环节，降低实测排障成本

- 日期：2026-03-19
- 修改人：Copilot
- 变更任务 ID：C02
- 变更文件：src/gui/integrated_recording_interface.py
- 指标变化：实时入口新增自动 Stage2 预分离兜底（无 track_sources 时触发）；诊断区新增红色阻断提示（无副轨源/暂停阻断/叠加关闭）
- 结论：直接点“实时分析”也可自动尝试生成伴唱轨，失败时给出明确阻断原因
