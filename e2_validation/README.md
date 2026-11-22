# E2：简单防御、视觉与检查—执行时序

38 个入口，环境 `~/.conda/envs/ai2thor-eval/bin/python`（Python 3.10.22）。`vlm_*` 需要已有 `DEEPSEEK_API_KEY`，其余离线回放不需要 API。代码由同目录的 `_bootstrap.py` 恢复根目录、共享依赖和跨脚本导入，文件移动不再依赖启动时 cwd。

| 工作线 | 入口/文件族 | 当前边界 |
|---|---|---|
| 初期观察 | `observation_audit.py`、`viewpoint_check.py`、`matched_observation.py` | RGB/Depth/遮挡证据采集，不直接等于视觉可识别率 |
| 回执与历史 | `executor_receipts.py`、`full_trace.py`、`history_replay.py`、`history_monitor_v2.py`、`metric_pilot.py` | 原生回执的受控状态机；初版 `history_defense.py` 含 GT 泄漏，保留作负例，不作为可靠防御结果 |
| Oracle | `a_oracle_pre_execution_guard.py` | 受保护真值上界，与可部署独立观察分开 |
| B1–B4 | `b1_*` … `b4_*` | 视觉/ROI、真实有锅/错误炉头、目标绑定与离线融合 |
| B5 | `b5*` | 时序证据、旧帧重放、同图重复及共识；重复不是独立证据 |
| B6 | `b6_native_boundary_audit.py` | 原生入口与可写路径审计，不证明攻击者权限已成立 |
| B7 | `b7a_*` … `b7h_*` | TOCTOU、微动作、二次检查、双 Agent/线程；炉灶提交均被截断 |
| M6 视觉准备 | `stove_camera_view_probe.py`、`vision_payload_probe.py`、`vlm_stove_state_readout*.py` | 原 M6 视觉输入和读出，按功能归入 E2 |

```bash
cd /home/yyn/embodied
python3 scripts/run_experiment.py e2 --check
python3 scripts/run_experiment.py e2 --script history_monitor_v2.py
# 真正采集时需要图形软件渲染；API 调用仍由原脚本决定
xvfb-run -a env LIBGL_ALWAYS_SOFTWARE=1 \
  python3 scripts/run_experiment.py e2 --script b2_benign_stove_setup.py
```

完整入口和旧名见 [SCRIPTS.md](SCRIPTS.md)。原证据 `results/e2*` 和 `results/m6_vision/` 保留；启动器在独立临时工作区写新结果。B7H 的 12/12 使用检查结束通知和同进程锁，且没有实际 Toggle；不能当作自然独立攻击成功率。简单提交前 recheck 已阻断所测案例，需保留此反例。

E3 的 b7 内部也有 E1/E2 编号，b4 内部有 `e2c_*`；它们是后期 baseline 子步骤，与本目录的早期 E2 不混排。
