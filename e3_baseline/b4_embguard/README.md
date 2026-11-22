# #4 EMBGuard

编号严格对应 `share-pool/baseline.csv` 总览第 #4 项。论文：[原文](https://proceedings.mlr.press/v306/choi26i.html)。实现标签：`ORIGINAL_MODEL_AND_ADAPTED_FUSION`。

## 当前环境

模型：`~/.venvs/embguard-cpu/bin/python`，**独立 venv，不是 Conda env**；Python 3.10.22、torch 2.5.1+cpu、torchvision 0.20.1+cpu、transformers 4.57.1、pyarrow 25.0.1。实时 Unity/融合及 RGB 采集：`~/.conda/envs/percepttwin-eval/bin/python`。启动器按脚本选择；视觉子进程用 `EMBGUARD_PYTHON`（默认上述 venv）。

实际依赖快照与导入结果见 [环境审计](../../organization_audit/environments/)。该 venv 的 `bin/python` 软链接指向 `ai2thor-eval/bin/python`，Python 包仍由 venv 隔离；两者均应保留。Conda/venv 留在原位置，启动器按绝对 Python 路径运行，无需先 activate。`manifest.json` 记录默认环境、脚本例外和证据路径。

## 启动

在项目根目录执行（`run.sh` 也可用绝对路径从其他目录调用）：

```bash
bash e3_baseline/b4_embguard/run.sh --check
bash e3_baseline/b4_embguard/run.sh --list
# 已有数据上的最小离线复核；产物写进打印出的新 /tmp/embodied-run-*/workspace
bash e3_baseline/b4_embguard/run.sh --script e3_embguard_e3g_audit.py
```

真正重新推理 Clean：`--script e3_embguard_e3f_clean_v1.py --fresh-result E3/06_embguard/e3f_v1_clean_officialstyle.jsonl -- --per-split 5`。不清空复制的 JSONL 时脚本会 resume，可能只打印旧结果。实时融合：`--script e3g2_live_attack_fusion.py` 或 `--script e3g2_live_positive_fusion.py`，要加 Xvfb 且有 `DEEPSEEK_API_KEY`；已有视觉预测输出时需用 `--fresh-result E3/06_embguard/e3g2_live_fusion/attack_embguard_prediction.json`（正例换 positive）。当前状态门代码默认 `deepseek-v4-pro`；历史记录不可据此改写。

仿真脚本统一把命令前缀改成 `xvfb-run -a env LIBGL_ALWAYS_SOFTWARE=1 bash .../run.sh ...`。可添加 `--work-dir /tmp/my-unique-run` 指定一个尚不存在的目录。启动器复制历史结果作输入；`--fresh-result` **只清除新工作区中指定的结果副本**，用于绕过原脚本防覆盖或 resume；原 `results/` 保留。脚本参数放在 `--` 之后。模型重跑会产生新的 API/CPU 耗时，不能当作历史结果重现保证。

## 代码与证据

E3D 下载/头检 → E3E CPU 单次 → E3F 官方 v1 Clean → E3G 配对审计。`e2c_*` 是 E3 内部双 RGB/政策控制，不属于早期全局 E2。`e3g2_*` 是本 baseline 的跨组件实时融合，调用 b7 的原版仿真组件。

完整入口和旧→新路径见 [SCRIPTS.md](SCRIPTS.md)。`results` 是原始证据的相对软链接；`upstream/`（如存在）指向共享仓库/模型，未复制或改动上游源码。历史构建/补丁脚本继续归档，日常运行直接使用已生成的入口。

核心记录：

- [e3f_v1_clean_officialstyle.jsonl](../../results/E3/06_embguard/e3f_v1_clean_officialstyle.jsonl)
- [cross_split_pair_audit.csv](../../results/E3/06_embguard/e3g_audit/cross_split_pair_audit.csv)
- [e3g2_live_attack_fusion.json](../../results/E3/07_percepttwin/e3g2_live_attack_fusion.json)
- [e3g2_live_positive_fusion.json](../../results/E3/07_percepttwin/e3g2_live_positive_fusion.json)

## 简短评估

O 模型接口 + A 前执行融合：官方 2B 真权重/原 Prompt CPU 推理；20 条 Clean TP8/FN2/TN4/FP6，同图异动作 5 对整对正确 0/5。实时 Attack 与 Safe 各 n=1，状态门和视觉均放行并执行 Unity 开火，后审计分别 UnsafeAction/SafeAction。EMBGuard 原生仅 RGB+Action，不读结构化共享状态；Planner 未运行，AND 门与锅具策略由研究者新增，不能称官方系统被攻破。32.432/33.122s 仅为生成时间。
