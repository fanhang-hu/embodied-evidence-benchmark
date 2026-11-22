# E5 当前阅读入口（2026-10-23）

用户提出的四阶段框架已采用，并保留原 exp-5 编号映射：[E5_WORKPLAN.md](E5_WORKPLAN.md)。最新实际执行和恢复结果见 [E5_FOLLOWUP_GUIDE.md](E5_FOLLOWUP_GUIDE.md)。

- 第一轮来源/目标/回执授权探针：[E5_GUIDE.md](E5_GUIDE.md)。这是历史阶段边界，仍保持原样。
- 最新原生任务恢复：`results/E5/task_recovery/native_20261023_02/`，80 配对回合；报告在 `results/E5/02_summary/task_recovery_20261023_02/`。
- 真实变化后的离线缓存对照：`results/E5/staleness/native_trace_20261023_01/`，8 条原生变化、40 探针判断。
- 原恢复 v1 仍保留：`results/E5/task_recovery/native_20261023_01/`；工程修订见 [E5_RECOVERY_AMENDMENT.md](E5_RECOVERY_AMENDMENT.md)。

正式五组安全任务完成数为 16、6、11、16、16（各分母 16），全部无违规执行。恢复模型为严格匹配公开输入的归档真实 DeepSeek 响应，不是新在线调用。真实部署权限、自然并发/TOCTOU、独立传感器/ROI 和在线生成成本仍未建立。
