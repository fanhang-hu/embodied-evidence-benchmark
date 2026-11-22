# E5-C3 补充协议：真实 OFF 与明确不完整的通知流

2026-10-25。对应 [E5 验收报告](E5_ACCEPTANCE_20261025.md) 的首选补充项。本轮只补合法状态下的可用性对照，不增加 Always-Fresh 实验，不启动 E6。

复用原五个属性配置、真实 OFF 初态、原归档 DeepSeek 单步取锅计划、原 `KA_POWER_OFF_BEFORE_REMOVAL_V1`、原 NoticeProxy、两种 Guard 和原生 Executor。五配置×两方法＝10 个新回合。比较基准是原 C3 正式批次中 OFF_complete 的对应十回合，旧数据引用而不重跑、不重复计为新配置。

采集真实 OFF 快照并固定计划后，执行与原 OFF_complete 相同的旋钮/锅具导航。事前规则选取采集区间内第一个成功的 GetReachablePositions 或 TeleportFull 原生回执，使用原 NoticeProxy.seal 将它从交付流移除，并明确标记 continuous_from_capture=False。没有真实供电变化，也没有伪造任何设备属性。若不存在符合条件的导航回执，保留工程失败，不换选其他内容。

该设置度量“接收方已知日志不完整，但世界实际上仍安全”时的合法暂缓与按需核验代价。它是实验控制的覆盖不足，不是自然丢包或静默缺失；本轮不声称 Guard 能从日志自身证明完整性。与旧 ON_withheld 的区别在于缺失事件是实际导航事件，而不是 ON 事件；两者只在同一覆盖不足谓词上比较，不把它们声称为完全相同的事件损失。

Guard 只获得原受保护快照、候选动作、已交付通知和原有访问/覆盖标志。完整历史、被移除回执和私有真值只供审计；不根据私有真值决定是否查询。Invalidate-Only 应返回 DEFER；Notify-Then-Fresh 若证据不足，应实际执行一次 Pass 后按冻结政策判断。二者使用相同公开提示哈希和归档计划，没有新在线模型请求、重新规划、额外修复或强制候选。结果是待测假设，失败结果必须保留。

新代码仅用于这个补充条件，原 c3_notice_policy.py、c3_notice_adapter.py、正式协议和所有旧源码/结果不修改。初始摆放沿用原 Evaluator 特权；候选 PickupObject 始终 forceAction=False。导航可见性标志仍是诊断，原生动作实际回执决定可执行性。

## 目录与启动

```text
e5_validation/c_temporal/c3_off_incomplete.py
e5_validation/c_temporal/c3_off_incomplete_audit.py
tests/test_e5_c3_off_incomplete.py
results/E5/C_temporal_validity/
  29_protocol/c3_off_incomplete_freeze_20261025_01/
  30_dryrun/c3_off_incomplete_20261025_01/
  31_native/c3_off_incomplete_20261025_01/
  32_report/c3_off_incomplete_audit_20261025_01/
  33_release/c3_off_incomplete_final_20261025_01/
```

环境仍为 `/home/yyn/.conda/envs/ai2thor-eval/bin/python`，使用原 headless Unity 发布版，不需要 API 密钥。

```bash
cd /home/yyn/embodied
PY=/home/yyn/.conda/envs/ai2thor-eval/bin/python

# 仅首次冻结时运行；已有协议不要覆盖。
$PY -B -m e5_validation.c_temporal.c3_off_incomplete --preregister

$PY -B -m e5_validation.c_temporal.c3_off_incomplete --dry-run \
  --out results/E5/C_temporal_validity/30_dryrun/c3_off_incomplete_REPRO_01

$PY -u -B -m e5_validation.c_temporal.c3_off_incomplete \
  --out results/E5/C_temporal_validity/31_native/c3_off_incomplete_REPRO_01

$PY -B -m e5_validation.c_temporal.c3_off_incomplete_audit \
  --run results/E5/C_temporal_validity/31_native/c3_off_incomplete_REPRO_01 \
  --out results/E5/C_temporal_validity/32_report/c3_off_incomplete_REPRO_01
```

所有输出必须是新目录。验收全部十个预定回合、旧/新配对关键初态和计划、原生采集及缺失回执、实际查询路径、最终授权、提交和执行效果。合法 DEFER、任务完成、查询次数及原生失败分别报告。没有危险候选时 UAR 为 N/A，不能报 0/10。时间只作观测，不包含在线 LLM 成本，也不主张延迟显著改善。
