# #7 PerceptTwin

编号严格对应 `share-pool/baseline.csv` 总览第 #7 项。论文：[原文](https://arxiv.org/abs/2606.04226)。实现标签：`ADAPTED_COMPONENT`。

## 当前环境

`~/.conda/envs/percepttwin-eval/bin/python`（Python 3.10.22、JAX 0.5.0 CPU、OpenAI 2.54.0、AI2-THOR 开发版 `0+8524eadda94df0ab2dbb2ef5a577e4d37c712897`）。该环境不是主 `ai2thor-eval` 的5.0.0。缓存 Unity Player 在 `~/.ai2thor/releases/`；上游 `external/PerceptTwin` 和 fork 未移动。

实际依赖快照与导入结果见 [环境审计](../../organization_audit/environments/)。Conda/venv 留在原位置，启动器按绝对 Python 路径运行，无需先 activate。`manifest.json` 记录默认环境、脚本例外和证据路径。

## 启动

在项目根目录执行（`run.sh` 也可用绝对路径从其他目录调用）：

```bash
bash e3_baseline/b7_percepttwin/run.sh --check
bash e3_baseline/b7_percepttwin/run.sh --list
# 已有数据上的最小离线复核；产物写进打印出的新 /tmp/embodied-run-*/workspace
bash e3_baseline/b7_percepttwin/run.sh --script e3_percepttwin_p1_preflight.py
```

可信重查仿真入口：`--script e3_percepttwin_e2_fresh_recheck.py`；正例 `--script e3_percepttwin_e2b_positive_control.py`，均需 Xvfb 和既有 `DEEPSEEK_API_KEY`。目前相关代码默认 `deepseek-v4-pro`，历史日志按其实际模型记录。真正原生 Hydra/WandB 全循环、A* 和资产重建未复现。

仿真脚本统一把命令前缀改成 `xvfb-run -a env LIBGL_ALWAYS_SOFTWARE=1 bash .../run.sh ...`。可添加 `--work-dir /tmp/my-unique-run` 指定一个尚不存在的目录。启动器复制历史结果作输入；`--fresh-result` **只清除新工作区中指定的结果副本**，用于绕过原脚本防覆盖或 resume；原 `results/` 保留。脚本参数放在 `--` 之后。模型重跑会产生新的 API/CPU 耗时，不能当作历史结果重现保证。

## 代码与证据

P1–P18 准备 → P19–P21 技能/状态/后审计 → P22 终态 → P23 规划 → P24-B 执行 → P25 反馈；E1-E/F 是研究者前置门，E2-A/B 是可信重查。此处 E1/E2 是 E3 的子实验编号，与根目录早期 E1/E2 分开。

完整入口和旧→新路径见 [SCRIPTS.md](SCRIPTS.md)。`results` 是原始证据的相对软链接；`upstream/`（如存在）指向共享仓库/模型，未复制或改动上游源码。历史构建/补丁脚本继续归档，日常运行直接使用已生成的入口。

核心记录：

- [p24b_native_plan.json](../../results/E3/07_percepttwin/p24b_native_plan.json)
- [p25_feedback_replan.json](../../results/E3/07_percepttwin/p25_feedback_replan.json)
- [e2_corrupted_freshcheck.json](../../results/E3/07_percepttwin/e2_corrupted_freshcheck.json)
- [e2b_clean_positive.json](../../results/E3/07_percepttwin/e2b_clean_positive.json)

## 简短评估

O/A 组件复现：原版 gen_plan、apply_skill、执行后 Judge 和反馈重规划；GoTo 用 TeleportFull，几何同步有定点适配。P24-B 四步任务成功、炉头始终 OFF；P25 新计划未再执行。E2-A 同 Unity fresh query 阻断污染，E2-B 有锅放行。该重查为 Oracle-like 强对照。炉灶执行前门及政策是新增；Unity 中执行后的 Judge 不能被解释为真实机器人执行前防护失效。
