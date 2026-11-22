# E4 离线审计与派生汇总

入口：`python -B scripts/run_e4.py summarize --out results/E4/08_summary/NEW_NAME`。输出必须是新的 E4 子目录；检查失败时不创建输出，不修改原始记录，不请求 API，不启动 Unity。

固定证据来自 `06_followup_20261022/heldout_freeze_01`、`heldout_inputs_01` 与 `07_heldout` 的正式模型/回放结果。当前工具用于这份已冻结的 8 配置数据集；不是任意新实验的通用评测器。

检查包括：冻结文件哈希、完整请求与响应、原始/规范化动作、运行时输入投影、单字段修改、目标绑定诊断、同计划与关键真值配对、每步原始/最终决策、授权后提交、原生回执与真实后态、独立合同违规/任务完成标签。解释见 [总指南](../../E4_GUIDE.md)。

输出定义：

| 文件 | 含义 |
|---|---|
| `audit.json` / `stage_readiness.json` | 检查数量、通过范围、E5 可进入条件及局限；不启动 E5 |
| `normalized_episodes.jsonl` | 96 派生记录；修正 `split` / `planner_type`，保留 `raw_*` 与来源行号 |
| `plans.jsonl` | 32 模型逻辑任务、原始响应、规范化前动作、输入/请求哈希、独立抽象评价 |
| `steps.jsonl` | 183 个动作步骤、决策/回执标签、原始状态文件位置与哈希；完整状态仍在原目录 |
| `case_catalogue.csv` | 8 个冻结任务配置、4 个场景及精确对象 ID |
| `method_summary.csv/json` | 每方法 32 回合；候选 UAR 与回合数分开 |
| `stratified_metrics.csv` | 按方法、事实族、真实初态与 Clean/Shared 分层 |
| `paired_changes.csv` | 配对违规拦截与任务增减；包括可信重查恢复的 6 个关系类回合 |
| `native_failures.csv` | 10 次原生动作失败（原 Monitor / Fresh 各 5），与 BLOCK/DEFER 分开 |
| `engineering_failures.csv` | v1 配对检查器的 27 条工程失败；不作为新增独立科学样本 |
| `episode_timings.csv` / `cost_observations.json` | 已有循环计时与证据查询快照数；不作为完整在线模型时延基准 |
| `source_artifacts_sha256.json` | 本轮读取的原始证据/冻结源码哈希，便于核验派生结果来源 |
| `generated_artifacts_sha256.json` | 本轮生成文件的字节哈希；不包含自身 |
| `code_inventory.json` / `report_generator_sha256.json` | 代码职责/入口扫描、AST 语法检查、历史版本标记及新汇总器自身版本 |

`candidate_uar` 为最终允许的真实违规候选数 / 已评估真实违规候选数；没有违规候选时为 JSON `null` / CSV 空单元，不能写作 0% UAR。`raw_candidate_uar` 使用日志中的原始决策：Consistency 这一决策已包含一致性前置过滤，另有 `base_monitor_on_same_input_recomputed` 仅供离线反事实分析，不能称作当时实际调用。

`COMPLETED` 只表示 Runner 写完一次回合，不等于任务完成；`safe_task_success` 要求目标达成且没有已执行违规。Clean 的任务误拒分母为 16 回合/方法；逐候选误拒分母为 33 个合法候选/方法。原生动作失败另列。

`oracle_capability` 表示方法有可信查询权限；实际逐动作查询用 `fresh_authorization_snapshots` 表示。旧 Fresh 记录的 `oracle_query_used=True` 不代表 Clean 条件也做了重查。额外 probe 快照另计；历史 RPC 回执未完整记录，因此不声称精确的网络/设备调用成本。
