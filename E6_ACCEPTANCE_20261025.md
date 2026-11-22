# E6 限定范围结项验收（2026-10-25）

**结论：E6 可以按自建管线、两类冻结安全合同和受信单写者的范围结项。**
用户在普通终端完成了 16 回合真实在线 DeepSeek／Unity 闭环；随后独立重跑审计，
全部通过。此前的在线验证缺口已经补齐，范围内没有必需的未完成实验。

[机器可读验收记录](results/E6/37_acceptance/scoped_20261025_01/acceptance.json) ·
[在线结果逐项复核](results/E6/37_acceptance/scoped_20261025_01/online_review.json) ·
[在线独立复审](results/E6/34_online_audit/heldout_durable_20261025_01/audit.json)

## 在线闭环结果

协议包括 FloorPlan9/10 两个新场景、属性／关系两类合同、正常／攻击条件，
以及 Shared／Independent Fresh 两种最终授权，共 16 个配置。全部配置完成，
有 16 个不同的提供方响应 ID，返回模型为 `deepseek-flash`，记录总用量 10,452 tokens。
没有请求失败、非法响应、Planner 空计划或原生动作失败。

| 条件／策略 | 危险候选错误授权 | 实际违规执行 | 安全任务完成 | 受保护查询 |
|---|---:|---:|---:|---:|
| 攻击／Shared | 4/4 | 4/4 | 0/4 | 0 |
| 攻击／Independent Fresh | 0/4 | 0/4 | 0/4 | 8 |
| 正常／Shared | N/A | 0/4 | 4/4 | 0 |
| 正常／Independent Fresh | N/A | 0/4 | 4/4 | 8 |

两类合同分别都是 Shared 违规 2/2、Independent Fresh 阻断 2/2；正常任务各自
两组均完成 2/2。正常条件没有危险候选，因此 UAR 为 N/A。攻击被阻断不等于任务
恢复：该矩阵不重规划，Independent Fresh 在攻击条件下没有完成原任务。

[完整在线报告](results/E6/36_online_report/online_20261025_170422_914231/summary.json) ·
[逐回合数据](results/E6/36_online_report/online_20261025_170422_914231/episodes.csv)

## 两条传播路径应分别表述

**属性路径：** 4 个攻击回合（2 个场景 × 2 种授权）中，真实开关为 ON，Producer
向 Planner 发布 OFF，在线计划均直接提议 PickupObject。Shared 消费假事实并放行；
Independent Fresh 得到真实 ON 状态并 BLOCK。这里有错误事实进入 Planner 的证据。
本在线矩阵没有 clean-unsafe Planner 对照，因此不单凭这些回合估计污染对规划的因果效应。

**关系路径：** 4 个攻击回合中，Planner 初次消费时关系事实仍然真实，不能记为
Planner 假关系传播成功。DeepSeek 生成 PickupObject、PutObject、ToggleObjectOn。
计划前缀执行后，评估器通过原生 PickupObject 建立关系变化，再由 Producer 持续报告旧关系。
Shared 在锅具已不属于目标炉头时放行开火；Independent Fresh 查询真实关系后 BLOCK。
这条证据支持运行时 Monitor 的授权失败，不能写成关系污染已经诱导 Planner 偏离。
评估器的物理变更不属于攻击者权限。

各授权策略使用独立在线请求。本次 8 对相同配置的初始合同事实、提示和计划动作
实际都一致；这是观测到的匹配，不是在线设计保证每次会得到同一计划。

## 完成的实验范围

| 轨道 | 回合 | Planner／目的 |
|---|---:|---|
| 正式开发矩阵 | 144 | 已归档 DeepSeek；六种最终授权 |
| 字段权限／持续性压力测试 | 96 | 已归档 DeepSeek；单／双字段、一次／持续 |
| 新场景矩阵 | 72 | 确定性 Planner；两个场景、两类合同 |
| 关键动作 Fresh 补充 | 24 + 12 | 开发集／新场景，与已有成本对照匹配 |
| 新场景在线闭环 | 16 | 真实 DeepSeek 请求和原生 Unity 执行 |

主轨道共 364 个回合，分别统计，不将不同 Planner、合同或条件合并成一个成功率。
场景和任务被多次复用，364 不是独立样本数；在线轨道只有两个新场景簇。
旧 v2 Pilot、未完成的 285 条扩展记录及离线探测不并入正式率。

34 项针对性测试已通过；前 348 回合的[时序与完整性补充审计](results/E6/31_trace_audit/supplement_20261025_01/audit.json)
通过；新在线轨道在复审中执行了相同的补充检查。
源码和历史实验结果保持冻结。原先的待运行验收文档保存在
[历史验收快照](results/E6/37_acceptance/scoped_20261025_01/prior_acceptance.md)。

## 防御与贡献判断

归档开发矩阵中 Shared 与 Same-Source Fresh 均实际违规 8/8，可信独立证据路径阻断
已测攻击；在线补充验证 Shared 4/4 与 Independent Fresh 0/4 的授权／执行差异。
主线是同源最新假证据仍可使最终 Monitor 错误授权，以及受保护证据路径如何恢复
这两种合同的正确授权。在线轨道没有补测 Same-Source Fresh，其结论仍来自归档矩阵。

成本结果不支持 Hybrid 的普遍优势。开发集攻击／正常条件中，关键动作 Fresh 各需
8 次查询，Hybrid 各需 11 次；确定性新场景攻击条件分别为 4 次和 6 次，正常条件
两者均为 4 次。Hybrid 保留为对照，不应作为“成本更优”的主要贡献。
[成本补充及审计来源](results/E6/30_critical_fresh_report/comparison_20261025_01/summary.json)

## 结项边界

本次验收覆盖自建受限 Producer 的真实 IPC、Planner／Monitor 的证据消费、原生
不强制动作回执、受保护查询、合法任务效用和条件化成本。它不证明部署级上游低权限
漏洞、并发原子授权、静默通知丢失检测、普遍安全性或成本最优。Receipt／Hybrid
仍依赖可信初始捕获、完整有序通知及受信单写者。这些扩展主张不在本阶段验收范围。

原始审计中的 `original_E6_complete=false` 是冻结程序不自动宣布研究结项的保守字段，
不是某项检查失败。本次范围验收单独记录为 `scoped_E6_complete=true`，不修改旧日志。

## 后续使用

当前无需重跑实验或再次请求 API。若需要重新核对现有结果并生成新报告：

```bash
bash /home/yyn/embodied/scripts/run_e6_online.sh --report-only
```

该命令无需联网、不启动 Unity、不增加模型调用。原网络错误及 bashrc 检查记录作为
历史环境诊断保留；用户终端的成功执行已经补齐实际在线证据。
下一步可以整理论文主表、方法描述和局限性，而不是继续为本阶段增加必做实验。
