# #9 Mind the Refinement Gap

编号严格对应 `share-pool/baseline.csv` 总览第 #9 项。论文：[原文](https://arxiv.org/abs/2610.02662)。实现标签：`ADAPTED_COMPONENT`。

## 当前环境

`~/.conda/envs/refinement-gap-eval/bin/python`（Python 3.11.17、Spot 2.16.1、NumPy 2.4.6、SciPy 1.17.1、OpenAI 3.35.1）。复用原 `external/SPINE` 与 `external/RoboGuard`。

实际依赖快照与导入结果见 [环境审计](../../organization_audit/environments/)。Conda/venv 留在原位置，启动器按绝对 Python 路径运行，无需先 activate。`manifest.json` 记录默认环境、脚本例外和证据路径。

## 启动

在项目根目录执行（`run.sh` 也可用绝对路径从其他目录调用）：

```bash
bash e3_baseline/b9_refinement_gap/run.sh --check
bash e3_baseline/b9_refinement_gap/run.sh --list
# 已有数据上的最小离线复核；产物写进打印出的新 /tmp/embodied-run-*/workspace
bash e3_baseline/b9_refinement_gap/run.sh --script e3_refinement_r5l_finalize.py
```

Planner 入口 `--script e3_refinement_r5e_real_planner.py`；需 `OPENAI_API_KEY`（可以在本机设为既有 DeepSeek key）、`OPENAI_BASE_URL=https://api.deepseek.com`、`SPINE_MODEL=deepseek-flash`。启动器为后两项提供默认值，不更改历史代码原来 gpt-4o 的默认值；不会读取/打印密钥。

仿真脚本统一把命令前缀改成 `xvfb-run -a env LIBGL_ALWAYS_SOFTWARE=1 bash .../run.sh ...`。可添加 `--work-dir /tmp/my-unique-run` 指定一个尚不存在的目录。启动器复制历史结果作输入；`--fresh-result` **只清除新工作区中指定的结果副本**，用于绕过原脚本防覆盖或 resume；原 `results/` 保留。脚本参数放在 `--` 之后。模型重跑会产生新的 API/CPU 耗时，不能当作历史结果重现保证。

## 代码与证据

R1/R2 人工图和隐式动作 → R3 原版图/路径（保留阴性结果） → R4 细化门 → R5A–D 原回调/共享消费者 → E/F/G 真 Planner → H/I 简防 → J/K 运行时与初始化边界 → L 汇总。

完整入口和旧→新路径见 [SCRIPTS.md](SCRIPTS.md)。`results` 是原始证据的相对软链接；`upstream/`（如存在）指向共享仓库/模型，未复制或改动上游源码。历史构建/补丁脚本继续归档，日常运行直接使用已生成的入口。

核心记录：

- [r5l_final_summary.json](../../results/E3/09_refinement_gap/r5l_final_summary.json)
- [r5jk_boundary_final.json](../../results/E3/09_refinement_gap/r5jk_boundary_final.json)

## 简短评估

A 组件评估；与 b1 共用原组件及 perch_small 地图，并非第九个独立机器人系统。论文关注 surface/refined 轨迹完整性；R5 扩展另测共享语义别名。8任务16调用，危险严格配对3/4、安全6/6；可信参考和图内冲突检查都把误授3降为0。J/K 7/7 为接口能力，不是敌手拥有真实 ROS 权限；无机器人导航执行。
