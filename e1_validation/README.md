# E1：共享状态污染机制验证

11 个入口，主要环境 `~/.conda/envs/ai2thor-eval/bin/python`（Python 3.10.22、AI2-THOR 5.0.0）。共享依赖为 `external/SafeAgentBench` 和 `external/safe-hierarchical-embodied-ai`。文件名已按事实类型、授权/执行或入口验证重命名；完整旧名对应见 [SCRIPTS.md](SCRIPTS.md)。

| 工作线 | 入口 | 证据含义 |
|---|---|---|
| M1 | `scene_inventory.py`、`state_channel_isolation.py` | 场景发现、真实状态与 Planner/Monitor 副本隔离 |
| 属性 | `microwave_attribute_authorization.py`、`microwave_attribute_execution.py` | 错误 ALLOW 后，原生通电微波炉开门被模拟器拒绝 |
| 关系 | `creditcard_microwave_feasibility.py`、`microwave_relation_authorization_execution.py` | 含卡微波炉通电，原生动作成功并违反研究者合约 |
| 执行前边界 | `microwave_preexecution_interceptor.py` | 拦截原始动作提交，区分授权与执行 |
| M5 | `kitchen_native_state_corruption.py`、`kitchen_relation_geometry_consistency.py`、`kitchen_native_submission_boundary.py` | 原生炉灶规则、关系/位置一致污染、提交点截断 |
| M6 | `kitchen_state_provider_pipeline.py` | 子进程状态生产者和 Planner 代理；非完整 LLM Planner |

```bash
cd /home/yyn/embodied
python3 scripts/run_experiment.py e1 --check
python3 scripts/run_experiment.py e1 --list
xvfb-run -a env LIBGL_ALWAYS_SOFTWARE=1 \
  python3 scripts/run_experiment.py e1 \
  --script microwave_attribute_authorization.py
```

统一启动器在新的 `/tmp/embodied-run-*/workspace` 中复制证据并运行，不更改原 `results/`。这些脚本可启动模拟器并改变模拟状态；本次整理只验证路径与 IPC provider，不重新执行攻击。源结果继续使用 `results/e1a_*`、`results/m1_*`、`results/m5_*`、`results/m6_*` 历史文件名。

早期日志的 T0/T1/T2 分别表示 Clean / Planner-only / Shared **实验条件**；Proposal-3 的 T0/T1/T2 表示 **攻击者能力层级**，两套命名不能等同。这里有固定候选、研究者合约和 Planner 代理，不能将现有结果改写为原生低权限 Planner–Monitor 共同失陷。
