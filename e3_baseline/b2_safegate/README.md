# #2 SafeGate-inspired

编号严格对应 `share-pool/baseline.csv` 总览第 #2 项。论文：[原文](https://arxiv.org/abs/2604.05427)。实现标签：`MECHANISM`。

## 当前环境

`~/.conda/envs/ai2thor-eval/bin/python`（Python 3.10.22、AI2-THOR 5.0.0）。**Z3 5.3.1.0 原来是 pip --target 安装在 `results/E3/04_contract/safegate/deps/`，并不在 Conda site-packages**。启动层已加入该路径，`local_dependencies` 提供同一份依赖的快捷入口；无需重新安装。

实际依赖快照与导入结果见 [环境审计](../../organization_audit/environments/)。Conda/venv 留在原位置，启动器按绝对 Python 路径运行，无需先 activate。`manifest.json` 记录默认环境、脚本例外和证据路径。

## 启动

在项目根目录执行（`run.sh` 也可用绝对路径从其他目录调用）：

```bash
bash e3_baseline/b2_safegate/run.sh --check
bash e3_baseline/b2_safegate/run.sh --list
# 已有数据上的最小离线复核；产物写进打印出的新 /tmp/embodied-run-*/workspace
bash e3_baseline/b2_safegate/run.sh --script e3_safegate_m4_lifecycle.py --fresh-result E3/04_contract/safegate/m4_contract_lifecycle.json
```

仿真配对入口：`--script e3_safegate_m5_v2.py --fresh-result E3/04_contract/safegate/m5_paired_evaluation_v2.json`，外加 Xvfb 软件渲染前缀；依赖已保存 M1/M3/M4 和 e3b3 结果，不调用 LLM。

仿真脚本统一把命令前缀改成 `xvfb-run -a env LIBGL_ALWAYS_SOFTWARE=1 bash .../run.sh ...`。可添加 `--work-dir /tmp/my-unique-run` 指定一个尚不存在的目录。启动器复制历史结果作输入；`--fresh-result` **只清除新工作区中指定的结果副本**，用于绕过原脚本防覆盖或 resume；原 `results/` 保留。脚本参数放在 `--` 之后。模型重跑会产生新的 API/CPU 耗时，不能当作历史结果重现保证。

## 代码与证据

先 `e3b3_native_controller_guard.py`（原生规则/提交边界），再 M1 合同、M2 良性发现、M3 良性配对、M4 生命周期、M5_v2 汇总。M5 原稿与失败/无 TensorFlow 变体均保留。

完整入口和旧→新路径见 [SCRIPTS.md](SCRIPTS.md)。`results` 是原始证据的相对软链接；`upstream/`（如存在）指向共享仓库/模型，未复制或改动上游源码。历史构建/补丁脚本继续归档，日常运行直接使用已生成的入口。

核心记录：

- [m5_paired_evaluation_v2.json](../../results/E3/04_contract/safegate/m5_paired_evaluation_v2.json)
- [m4_contract_lifecycle.json](../../results/E3/04_contract/safegate/m4_contract_lifecycle.json)

## 简短评估

M：研究者实现 Guard / Invariant / Abort 与 Z3，非官方 SafeGate。4 个物理场景、8 个条件判定，危险污染 ALLOW 1/1，良性 Clean ALLOW 3/3，良性污染误拒 3/3，Native/Z3 一致 8/8。持续伪观察可使合同 HOLD；UNKNOWN 与 Oracle 能阻断。未复现完整 Hazard Binding、官方合同生成和真实 Abort。
