# #3 RoboSafe-inspired

编号严格对应 `share-pool/baseline.csv` 总览第 #3 项。论文：[原文](https://arxiv.org/abs/2512.21220)。实现标签：`MECHANISM`。

## 当前环境

`~/.conda/envs/ai2thor-eval/bin/python`（Python 3.10.22；OpenAI 1.52.2、HTTPX 0.27.2、AI2-THOR 5.0.0）。离线融合只需标准库。

实际依赖快照与导入结果见 [环境审计](../../organization_audit/environments/)。Conda/venv 留在原位置，启动器按绝对 Python 路径运行，无需先 activate。`manifest.json` 记录默认环境、脚本例外和证据路径。

## 启动

在项目根目录执行（`run.sh` 也可用绝对路径从其他目录调用）：

```bash
bash e3_baseline/b3_robosafe/run.sh --check
bash e3_baseline/b3_robosafe/run.sh --list
# 已有数据上的最小离线复核；产物写进打印出的新 /tmp/embodied-run-*/workspace
bash e3_baseline/b3_robosafe/run.sh --script e3_robosafe_r6a_fusion.py --fresh-result E3/05_optional/robosafe/r6a_fusion_v1.json
```

双源污染模型入口：`--script e3_robosafe_r6b.py --fresh-result E3/05_optional/robosafe/r6b_dual_corruption_swap_v1.json`；需要 `DEEPSEEK_API_KEY` 或 `ROBOSAFE_VLM_API_KEY`，可设 `ROBOSAFE_VLM_BASE_URL`、`ROBOSAFE_VLM_MODEL`，默认模型 `deepseek-flash`。

仿真脚本统一把命令前缀改成 `xvfb-run -a env LIBGL_ALWAYS_SOFTWARE=1 bash .../run.sh ...`。可添加 `--work-dir /tmp/my-unique-run` 指定一个尚不存在的目录。启动器复制历史结果作输入；`--fresh-result` **只清除新工作区中指定的结果副本**，用于绕过原脚本防覆盖或 resume；原 `results/` 保留。脚本参数放在 `--` 之后。模型重跑会产生新的 API/CPU 耗时，不能当作历史结果重现保证。

## 代码与证据

R2 采集 → R4A 视角 / R4B2 绑定 → R4B3/R4C 视觉与记忆 → R5A/B 历史 → R6A 离线融合 → R6B 双源污染。R4B1 的 v1/v2/v3 保留为协议迭代。

完整入口和旧→新路径见 [SCRIPTS.md](SCRIPTS.md)。`results` 是原始证据的相对软链接；`upstream/`（如存在）指向共享仓库/模型，未复制或改动上游源码。历史构建/补丁脚本继续归档，日常运行直接使用已生成的入口。

核心记录：

- [r6a_fusion_v1.json](../../results/E3/05_optional/robosafe/r6a_fusion_v1.json)
- [r6b_dual_corruption_swap_v1.json](../../results/E3/05_optional/robosafe/r6b_dual_corruption_swap_v1.json)

## 简短评估

M：自建视觉 Forward、历史 Backward、关键词记忆和融合；不是官方 RoboSafe。R6A 保留 Clean RGB 时纠错；R6B 同时替换跨场景 RGB/目标框及历史后，危险误授和良性误拒各 1/1。绑定有 simulator 协助，融合为离线，只有两个场景，无危险动作执行，未证明在线同场景敌手入口。
