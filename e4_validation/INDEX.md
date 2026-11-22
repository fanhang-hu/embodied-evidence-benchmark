# E4 代码索引（2026-10-23）

当前总指南：[E4_GUIDE.md](../E4_GUIDE.md)。统一入口：`python -B scripts/run_e4.py list`（从项目根目录执行）。旧 README 是受历史哈希清单保护的阶段文档；当前结论以总指南与新增汇总为准。

本次按执行阶段整理入口，并将离线审计与规范化汇总放入独立 `reporting/` 包。已冻结的科学代码保留原路径和文件内容，以维持历史 manifest、源码快照及重放脚本的可验证性。

| 分组 | 文件 | 使用范围 |
|---|---|---|
| 当前入口 | `workflow.py`、`../scripts/run_e4.py` | 按 offline / model / unity 分组转发原命令；不新增执行器 |
| 当前汇总 | `reporting/summary.py` | 只读逐步骤审计、规范化元数据、独立分母、CSV/JSON、E4 阶段评估 |
| 原生边界审计 | `audit.py` | AI2-THOR / SafeAgentBench 生产消费链与权限审计 |
| 物理可行性与绑定 | `feasibility.py`、`wrong_burner.py` | 真实动作正负对照、非目标炉头对照；历史场景发现入口 |
| 共同核心 | `simulator.py`、`protocol.py`、`pairs.py` | 物理设置/导航/执行、冻结合同/污染/Monitor、七条件配对协议；确定性 Planner 仅用于早期 Pilot |
| LLM Shadow | `llm_shadow.py`、`review_shadow.py`、`shadow_gate.py` | DeepSeek 输入投影/严格解析、归档复核、Pilot Unity 接入判据 |
| Pilot 五组 | `plan_replay.py`、`verify_plan_replay.py` | C0–C4 同计划回放与只读验收；FP2/3/4 |
| 无 Oracle 一致性 | `consistency.py`、`consistency_replay.py`、`verify_consistency.py` | 只读同一输入中的 Knob/Burner 布尔一致性，冲突 DEFER |
| Heldout 冻结 | `freeze_heldout.py`、`heldout_inputs.py` | 历史选取与冻结过程；复现优先使用已有清单，避免重新选择测试集 |
| Heldout 模型及评价 | `heldout_live.py`、`heldout_grade.py` | 32 逻辑任务 / 22 唯一请求；抽象合同评价；全部配置保留 |
| Heldout Unity | `heldout_pairs_replay.py`、`heldout_defense_compare.py` | 归档 LLM 计划回放及两种既有防御；复用 `pairs` 原 Monitor/Executor |
| 历史验证 | `verify.py` | 原始七条件 Pilot 84 条验收；会写入指定 run 的 `verified_summary.json`，不要对封存目录重复运行 |
| 用户补充审计 | `../scripts/e4_heldout_final_audit.py`、`../scripts/e4_independent_truth_audit.py` | 保留已有配对/独立真值核查；新版 `summarize` 包含相应检查并输出证据哈希 |
| 用户跨场景辅助 | `../scripts/e4_consistency_multiscene.py` | FP3/4 一致性回放；Heldout 复现使用分组入口 |
| 兼容入口 | `../scripts/e4_llm_planner_shadow.py`、`../scripts/e4_llm_plan_replay.py` | 保持旧命令可用 |
| 历史工程版本 | `heldout_defense_compare_v1.py`、`../scripts/patch_e4_defense_v2.py` | v1 全量原生 metadata 哈希误判；一次性补丁已应用。仅归档，勿再次启动/应用；当前文件为 v2 |

本包所有 `*.py` 都在上表按职责覆盖。`__pycache__/` 为 Python 自动生成缓存，不属于实验源码。外部项目、Conda 环境、Unity 二进制与 E1/E2/E3 不搬动。
