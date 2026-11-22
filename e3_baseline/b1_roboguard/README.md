# #1 RoboGuard

编号严格对应 `share-pool/baseline.csv` 总览第 #1 项。论文：[原文](https://arxiv.org/abs/2503.07885)。实现标签：`ADAPTED`。

## 当前环境

`~/.conda/envs/roboguard-e3/bin/python`（Python 3.10.22、Spot 2.16、OpenAI 3.6.0）；早期 M4 使用 `roboguard-eval`，同样保留在原处。

实际依赖快照与导入结果见 [环境审计](../../organization_audit/environments/)。Conda/venv 留在原位置，启动器按绝对 Python 路径运行，无需先 activate。`manifest.json` 记录默认环境、脚本例外和证据路径。

## 启动

在项目根目录执行（`run.sh` 也可用绝对路径从其他目录调用）：

```bash
bash e3_baseline/b1_roboguard/run.sh --check
bash e3_baseline/b1_roboguard/run.sh --list
# 已有数据上的最小离线复核；产物写进打印出的新 /tmp/embodied-run-*/workspace
bash e3_baseline/b1_roboguard/run.sh --script e3a3_offline_replay.py --fresh-result E3/01_roboguard/e3a3_offline_replay.json
```

在线复现：`--script e3a5_deepseek_live_pair.py`，需已有 `DEEPSEEK_API_KEY`。脚本仍用 `deepseek-flash`；原版 GPT-4o 未重现。

仿真脚本统一把命令前缀改成 `xvfb-run -a env LIBGL_ALWAYS_SOFTWARE=1 bash .../run.sh ...`。可添加 `--work-dir /tmp/my-unique-run` 指定一个尚不存在的目录。启动器复制历史结果作输入；`--fresh-result` **只清除新工作区中指定的结果副本**，用于绕过原脚本防覆盖或 resume；原 `results/` 保留。脚本参数放在 `--` 之后。模型重跑会产生新的 API/CPU 耗时，不能当作历史结果重现保证。

## 代码与证据

`e3a3_offline_replay.py` → `e3a4_failure_attribution.py` → `e3a5_deepseek_live_pair.py` → `e3a6_*` → `e3a7_precommitted_map.py`。`m4_*` 为早期探索，按原编号保留；不将早期失败控制组删掉。

完整入口和旧→新路径见 [SCRIPTS.md](SCRIPTS.md)。`results` 是原始证据的相对软链接；`upstream/`（如存在）指向共享仓库/模型，未复制或改动上游源码。历史构建/补丁脚本继续归档，日常运行直接使用已生成的入口。

核心记录：

- [e3_pair_consolidation.json](../../results/E3/01_roboguard/e3_pair_consolidation.json)
- [e3a7_precommitted_map.json](../../results/E3/02_simple/e3a7_precommitted_map.json)

## 简短评估

原生 SPINE 图与 RoboGuard LTL/Spot 路径，DeepSeek 替换 GPT-4o，属于 A。危险区域重标名保持坐标 (-4,28)。第一组在线 Clean BLOCK / Attack ALLOW；第二组 Clean 需要离线 LTL 语法修正，不能合并为两组在线成功。可信几何对照拦住 2/2；无真实导航及低权限上游写入证据。
