# M0：平台与技能可用性

本目录是平台检查，不属于九项安全 baseline。环境为 `~/.conda/envs/ai2thor-eval/bin/python`。脚本包括 AI2-THOR 启动/RGB、稳定性、长跑、对象交互、SafeAgentBench 数据/技能与危险任务可执行性测试。

```bash
cd /home/yyn/embodied
python3 scripts/run_experiment.py setup --check
xvfb-run -a env LIBGL_ALWAYS_SOFTWARE=1 \
  python3 scripts/run_experiment.py setup --script smoke_ai2thor.py
```

这些 `test_*.py` 是有顶层副作用的历史实验入口，**不是 pytest 单元测试**；不要用全仓 `pytest` 自动收集。逐个显式启动，产物在统一启动器打印的临时工作区。完整旧路径见 [SCRIPTS.md](SCRIPTS.md)。
